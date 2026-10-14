"""Turns classifier output into a decision, and combines evidence sources transparently.

Decision rules (also documented in the README and the "Detection Technology" page):

1. The classifier's AI-label score decides the category using two thresholds:
   score >= ai threshold -> Likely AI-Generated; score <= real threshold -> Likely
   Camera-Captured; anything in between -> Inconclusive.
2. If measured image characteristics make the classifier unreliable (very small
   image), a confident verdict is withheld and the result is Inconclusive.
3. A Content Credentials manifest whose validation state is "Trusted" and which
   declares that the image was created by generative AI overrides the classifier,
   because it is a verifiable statement by the signer. Untrusted/unsigned
   declarations, embedded generator strings and missing metadata never change
   the category; they are reported as separate evidence and as conflict notes.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings
from app.core.errors import AppError
from app.schemas import (
    CATEGORY_LABELS,
    Assessment,
    CalibrationInfo,
    ClassificationResult,
    LabelScore,
    MetadataResult,
    ModelInfo,
    ProvenanceResult,
    Reliability,
    ReliabilityFactor,
    ScoreInterpretation,
    Thresholds,
)
from app.services.classifiers.base import LabelProbability

logger = logging.getLogger("imageproof")

LOW_RES_SIDE = 128
REDUCED_RES_SIDE = 256
LOW_JPEG_QUALITY = 50


# --- calibration ------------------------------------------------------------------------
@dataclass(frozen=True)
class Calibration:
    method: str
    a: float
    b: float
    ai_threshold: float | None
    real_threshold: float | None
    fitted_on: str
    n_real: int | None
    n_ai: int | None
    created_at: str | None

    def probability(self, raw_ai_score: float) -> float:
        s = min(max(raw_ai_score, 1e-6), 1 - 1e-6)
        logit = math.log(s / (1 - s))
        z = self.a * logit + self.b
        return 1.0 / (1.0 + math.exp(-z))


def load_calibration(settings: Settings, model: ModelInfo) -> Calibration | None:
    """Load a calibration file written by ``python -m app.evaluation``.

    The file is only applied when it was fitted for exactly the model (and
    revision, when both are known) that is currently running.
    """
    if not settings.calibration_file:
        return None
    path = Path(settings.calibration_file)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data["model"]
        if meta.get("id") != model.name:
            logger.warning("calibration_ignored reason=model_mismatch")
            return None
        if meta.get("revision") and model.version and meta["revision"] != model.version:
            logger.warning("calibration_ignored reason=revision_mismatch")
            return None
        platt = data.get("platt") or {}
        thresholds = data.get("thresholds") or {}
        fitted = data.get("fitted_on") or {}
        return Calibration(
            method=str(data.get("method", "platt")),
            a=float(platt["a"]),
            b=float(platt["b"]),
            ai_threshold=float(thresholds["ai"]) if thresholds.get("ai") is not None else None,
            real_threshold=float(thresholds["real"]) if thresholds.get("real") is not None else None,
            fitted_on=str(fitted.get("description", "evaluation dataset")),
            n_real=fitted.get("n_real"),
            n_ai=fitted.get("n_ai"),
            created_at=data.get("created_at"),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("calibration_ignored reason=%s", type(exc).__name__)
        return None


# --- label mapping -----------------------------------------------------------------------
def map_labels(
    scores: list[LabelProbability], ai_labels: set[str], real_labels: set[str]
) -> tuple[float, list[LabelScore]]:
    if not ai_labels or not real_labels:
        raise AppError(
            503,
            "model_misconfigured",
            "The label mapping is not configured. Set IMAGEPROOF_AI_LABELS and IMAGEPROOF_REAL_LABELS.",
        )
    labelled: list[LabelScore] = []
    ai_total = 0.0
    seen_ai = seen_real = False
    for item in scores:
        key = item.label.lower()
        if key in ai_labels:
            role = "ai_generated"
            ai_total += item.score
            seen_ai = True
        elif key in real_labels:
            role = "camera"
            seen_real = True
        else:
            role = "other"
        labelled.append(LabelScore(label=item.label, score=round(item.score, 6), role=role))
    if not (seen_ai and seen_real):
        raise AppError(
            503,
            "model_misconfigured",
            "The configured label mapping does not match the labels returned by the model.",
            details={"model_labels": [s.label for s in scores]},
        )
    return min(max(ai_total, 0.0), 1.0), labelled


# --- thresholds / decision ------------------------------------------------------------------
def resolve_thresholds(settings: Settings, calibration: Calibration | None) -> Thresholds:
    if calibration and calibration.ai_threshold is not None and calibration.real_threshold is not None:
        return Thresholds(
            ai=calibration.ai_threshold,
            real=calibration.real_threshold,
            source="evaluation",
            validated=True,
            description=(
                f"Selected on an evaluation set ({calibration.fitted_on}). They are valid only for images that resemble that set."
            ),
        )
    return Thresholds(
        ai=settings.ai_threshold,
        real=settings.real_threshold,
        source="configured",
        validated=False,
        description=(
            "Conservative operator-configured thresholds. They have not been validated against an evaluation dataset for this deployment."
        ),
    )


def decide(ai_score: float, thresholds: Thresholds) -> str:
    if ai_score >= thresholds.ai:
        return "ai"
    if ai_score <= thresholds.real:
        return "camera"
    return "between"


def build_classification(
    scores: list[LabelProbability], model: ModelInfo, settings: Settings, calibration: Calibration | None
) -> ClassificationResult:
    ai_score, labelled = map_labels(scores, settings.ai_label_set, settings.real_label_set)
    thresholds = resolve_thresholds(settings, calibration)
    if calibration:
        interpretation = ScoreInterpretation(
            score_type="calibrated_probability",
            calibrated=True,
            description=(
                "The raw model score was mapped to an estimated probability with Platt scaling fitted on an evaluation set. "
                "The estimate is only meaningful for images similar to that set (same kinds of photos, generators and processing), "
                "and is not a probability that a specific image is authentic."
            ),
            calibration=CalibrationInfo(
                method=calibration.method,
                fitted_on=calibration.fitted_on,
                n_real=calibration.n_real,
                n_ai=calibration.n_ai,
                created_at=calibration.created_at,
                calibrated_ai_probability=round(calibration.probability(ai_score), 4),
            ),
        )
    else:
        interpretation = ScoreInterpretation(
            score_type="raw_softmax",
            calibrated=False,
            description=(
                "Raw output of the model's final softmax layer. It expresses how strongly the model prefers one label over the other. "
                "It is not calibrated: a score of 0.90 does not mean a 90% chance that the image is AI-generated, and models are often "
                "over-confident on images unlike their training data."
            ),
        )
    return ClassificationResult(
        model=model,
        ai_score=round(ai_score, 6),
        labels=labelled,
        interpretation=interpretation,
        thresholds=thresholds,
        decision=decide(ai_score, thresholds),  # type: ignore[arg-type]
    )


# --- reliability ------------------------------------------------------------------------------
def compute_reliability(
    *, width: int, height: int, source_format: str, jpeg_quality: float | None, exif_present: bool
) -> Reliability:
    factors: list[ReliabilityFactor] = []
    short = min(width, height)
    if short < LOW_RES_SIDE:
        factors.append(
            ReliabilityFactor(
                code="very_low_resolution",
                severity="limiting",
                message=f"The shorter side is only {short} px. Detectors are unreliable on such small images, so no confident verdict is given.",
            )
        )
    elif short < REDUCED_RES_SIDE:
        factors.append(
            ReliabilityFactor(
                code="low_resolution",
                severity="caution",
                message=f"The shorter side is {short} px. Low resolution removes detail that detectors depend on, which reduces reliability.",
            )
        )
    if source_format == "JPEG" and jpeg_quality is not None and jpeg_quality < LOW_JPEG_QUALITY:
        factors.append(
            ReliabilityFactor(
                code="heavy_jpeg_compression",
                severity="caution",
                message=f"Strong JPEG compression (estimated quality about {jpeg_quality:.0f}). Compression erases subtle cues and can mimic or hide them.",
            )
        )
    if source_format == "JPEG" and not exif_present:
        factors.append(
            ReliabilityFactor(
                code="no_exif",
                severity="info",
                message="No EXIF metadata. This commonly means the image was shared or re-saved, which can also have re-compressed it. It was not used in the assessment.",
            )
        )
    level = "standard"
    if any(f.severity == "limiting" for f in factors):
        level = "low"
    elif any(f.severity == "caution" for f in factors):
        level = "reduced"
    return Reliability(level=level, factors=factors)  # type: ignore[arg-type]


# --- final assessment -----------------------------------------------------------------------------
def build_assessment(
    classification: ClassificationResult,
    reliability: Reliability,
    provenance: ProvenanceResult,
    metadata: MetadataResult,
    settings: Settings,
) -> Assessment:
    trace: list[str] = []
    notes: list[str] = []
    t = classification.thresholds
    score = classification.ai_score
    trace.append(
        f"Classifier AI-label score {score:.3f}. Thresholds: Likely Camera-Captured at or below {t.real:.2f}, Likely AI-Generated at or above {t.ai:.2f} "
        f"({'evaluated' if t.validated else 'configured, not validated'})."
    )
    decision = classification.decision
    category = {"ai": "likely_ai_generated", "camera": "likely_camera_captured", "between": "inconclusive"}[decision]
    basis = "classifier"

    if reliability.level == "low" and decision != "between" and settings.degrade_low_reliability:
        category = "inconclusive"
        trace.append("A confident verdict was withheld because the image characteristics listed under reliability make the classifier unreliable.")

    if provenance.status == "trusted" and provenance.declares_ai_generation:
        if category != "likely_ai_generated":
            trace.append(
                "Verified Content Credentials from a trusted signer declare the image was created by generative AI. This overrides the classifier result."
            )
        else:
            trace.append("Verified Content Credentials from a trusted signer also declare the image was created by generative AI.")
        category = "likely_ai_generated"
        basis = "provenance"
    elif provenance.declares_ai_generation:
        notes.append(
            "Content Credentials found in the file declare that the image was created by generative AI, but the signer was not confirmed as trusted "
            "(or the manifest failed validation). The declaration is shown as evidence but did not change the assessment."
        )
    elif provenance.declares_partial_ai:
        notes.append(
            "Content Credentials record edits that include generative-AI content. The image may be a camera photo with AI-generated additions, "
            "which a whole-image classifier is not designed to detect."
        )

    if metadata.generator_signals and category == "likely_camera_captured":
        notes.append(
            "Embedded metadata mentions generation tooling while the classifier favours camera capture. Metadata is unauthenticated and can be forged or stale. Treat the evidence as conflicting."
        )
    if provenance.status in ("valid", "trusted") and provenance.declares_camera_capture and category == "likely_ai_generated" and basis == "classifier":
        notes.append(
            "Content Credentials declare a camera capture, but the classifier favours AI generation. The evidence conflicts. Neither source is conclusive."
        )

    headline = CATEGORY_LABELS[category]
    summary = _summary(category, basis, reliability, classification)
    return Assessment(
        category=category,  # type: ignore[arg-type]
        label=headline,
        basis=basis,  # type: ignore[arg-type]
        headline=headline,
        summary=summary,
        decision_trace=trace,
        reliability=reliability,
        notes=notes,
    )


def _summary(category: str, basis: str, reliability: Reliability, c: ClassificationResult) -> str:
    model = c.model.name
    if basis == "provenance":
        return (
            "Verified Content Credentials from a trusted signer declare that this image was created by generative AI. "
            "This is the signer's own verifiable statement, so it takes precedence over the visual classifier. "
            "It does not describe images that were edited afterwards by tools that do not update the credentials."
        )
    if category == "likely_ai_generated":
        return (
            f"The classifier ({model}) scored this image above the threshold for AI generation. That means its visual patterns resemble images the model learned to associate with AI generators. "
            "It is a statistical estimate, not proof, and photographs that are heavily processed or unlike the training data can be flagged in error."
        )
    if category == "likely_camera_captured":
        return (
            f"The classifier ({model}) did not find the patterns it associates with AI-generated images. "
            "That does not rule out AI generation: images from generators newer than the model's training data, or AI-assisted edits to a camera photo, may look camera-like to it."
        )
    if reliability.level == "low":
        return (
            "No confident verdict is given because the image's characteristics make the classifier unreliable. See the reliability factors for details."
        )
    return (
        "The classifier's score falls between the thresholds for camera and AI-generated images, so the evidence does not support a confident conclusion either way. "
        "Look at the other evidence sources and treat the result as unresolved."
    )
