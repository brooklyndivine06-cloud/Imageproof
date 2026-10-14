"""The analysis workflow: validate -> (classify | metadata | provenance | forensics) -> assess."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, UTC
from typing import Any, Awaitable, Callable, TypeVar

from app.config import APP_VERSION, Settings
from app.core.errors import AppError
from app.schemas import (
    AnalysisResponse,
    EvidenceSource,
    FileInfo,
    ForensicsResult,
    MetadataResult,
    ProcessingInfo,
    ProvenanceResult,
    StepRecord,
    Thresholds,
)
from app.services.assessment import (
    Calibration,
    build_assessment,
    build_classification,
    compute_reliability,
    resolve_thresholds,
)
from app.services.classifiers.base import (
    ClassifierFailure,
    ClassifierInput,
    ClassifierUnavailable,
    ImageClassifier,
)
from app.services.forensics import estimate_jpeg_quality, run_forensics
from app.services.metadata import extract_metadata
from app.services.provenance import inspect_provenance
from app.services.validation import ValidatedImage, validate_image

logger = logging.getLogger("imageproof")
T = TypeVar("T")

DISCLAIMER = (
    "Detection results are estimates produced by statistical models and automated checks. They are not proof of authenticity or of AI generation, "
    "and should not be the sole basis for editorial, legal, academic or other consequential decisions."
)


class AnalysisService:
    def __init__(self, settings: Settings, classifier: ImageClassifier, calibration: Calibration | None) -> None:
        self.settings = settings
        self.classifier = classifier
        self.calibration = calibration
        self._slots = asyncio.Semaphore(settings.max_concurrent_analyses)

    def thresholds_preview(self) -> Thresholds:
        return resolve_thresholds(self.settings, self.calibration)

    async def analyze(self, data: bytes) -> AnalysisResponse:
        try:
            await asyncio.wait_for(self._slots.acquire(), timeout=self.settings.queue_wait_seconds)
        except TimeoutError:
            raise AppError(
                503,
                "server_busy",
                "The server is handling other analyses. Try again in a moment.",
                retryable=True,
                headers={"Retry-After": "5"},
            ) from None
        try:
            return await asyncio.wait_for(self._run(data), timeout=self.settings.analysis_timeout_seconds)
        except TimeoutError:
            raise AppError(
                504,
                "analysis_timeout",
                "The analysis took too long and was stopped.",
                retryable=True,
            ) from None
        finally:
            self._slots.release()

    async def _run(self, data: bytes) -> AnalysisResponse:
        t0 = time.perf_counter()
        s = self.settings
        steps: list[StepRecord] = []

        started = time.perf_counter()
        image: ValidatedImage = await asyncio.to_thread(validate_image, data, s)
        steps.append(StepRecord(name="validate_and_decode", status="completed", duration_ms=_ms(started)))

        # Fail fast, before spending CPU on the other modules, if the classifier cannot serve this request.
        self._ensure_classifier_ready()

        async def classify() -> list[Any]:
            started_c = time.perf_counter()
            result = await self.classifier.classify(
                ClassifierInput(image_bytes=data, mime_type=image.mime_type, rgb=image.rgb)
            )
            steps.append(StepRecord(name="classifier", status="completed", duration_ms=_ms(started_c)))
            return result

        async def metadata() -> MetadataResult:
            return await asyncio.to_thread(extract_metadata, image.original, data)

        async def provenance() -> ProvenanceResult:
            if not s.enable_provenance:
                raise _Skipped("Provenance verification is disabled by configuration.")
            return await asyncio.to_thread(inspect_provenance, data, image.mime_type)

        async def forensics() -> ForensicsResult:
            if not s.enable_forensics:
                raise _Skipped("Visual forensics is disabled by configuration.")
            return await asyncio.to_thread(run_forensics, image.rgb, image.original, image.format)

        raw_task = asyncio.create_task(classify())
        meta_task = asyncio.create_task(self._optional("metadata", steps, metadata))
        prov_task = asyncio.create_task(self._optional("provenance", steps, provenance))
        fore_task = asyncio.create_task(self._optional("forensics", steps, forensics))

        all_tasks = (raw_task, meta_task, prov_task, fore_task)
        try:
            raw_scores = await raw_task
            metadata_result, provenance_result, forensics_result = await asyncio.gather(meta_task, prov_task, fore_task)
        except ClassifierUnavailable as exc:
            raise AppError(
                503, exc.code, str(exc), retryable=exc.retryable, headers={"Retry-After": "10"} if exc.retryable else None
            ) from None
        except ClassifierFailure as exc:
            headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
            raise AppError(502, "analysis_failed", str(exc), retryable=exc.retryable, headers=headers) from None
        finally:
            self._cancel(*all_tasks)

        model = self.classifier.model_info()
        classification = build_classification(raw_scores, model, s, self.calibration)

        meta_out = metadata_result or _empty_metadata()
        prov_out = provenance_result or _failed_provenance()
        fore_out = forensics_result or _unavailable_forensics()

        jpeg_quality = next((sig.value for sig in fore_out.signals if sig.id == "jpeg_quality"), None)
        if jpeg_quality is None and image.format == "JPEG":
            jpeg_quality = estimate_jpeg_quality(image.original)
        reliability = compute_reliability(
            width=image.width,
            height=image.height,
            source_format=image.format,
            jpeg_quality=float(jpeg_quality) if isinstance(jpeg_quality, (int, float)) else None,
            exif_present=meta_out.exif_present,
        )
        assessment = build_assessment(classification, reliability, prov_out, meta_out, s)

        response = AnalysisResponse(
            analysis_id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            app_version=APP_VERSION,
            processing=ProcessingInfo(duration_ms=_ms(t0), steps=steps),
            file=FileInfo(
                format=image.format,
                mime_type=image.mime_type,
                size_bytes=image.size_bytes,
                width=image.width,
                height=image.height,
                megapixels=round(image.width * image.height / 1_000_000, 2),
                color_mode=image.mode,
                sha256=image.sha256,
            ),
            assessment=assessment,
            classification=classification,
            evidence_sources=_evidence_sources(classification, meta_out, prov_out, fore_out, assessment.basis, steps),
            metadata=meta_out,
            provenance=prov_out,
            forensics=fore_out,
            limitations=_limitations(classification),
            disclaimer=DISCLAIMER,
        )
        logger.info(
            "analysis_complete id=%s category=%s basis=%s format=%s size_bytes=%d duration_ms=%d",
            response.analysis_id,
            assessment.category,
            assessment.basis,
            image.format,
            image.size_bytes,
            response.processing.duration_ms,
        )
        return response

    def _ensure_classifier_ready(self) -> None:
        state = self.classifier.status()
        if state.state == "ready":
            return
        mapping = {
            "not_configured": (503, "model_not_configured", False),
            "loading": (503, "model_loading", True),
            "error": (503, "model_unavailable", False),
        }
        status, code, retry = mapping[state.state]
        raise AppError(
            status,
            code,
            state.detail or "The detection model is not available.",
            retryable=retry,
            headers={"Retry-After": "10"} if retry else None,
        )

    async def _optional(self, name: str, steps: list[StepRecord], fn: Callable[[], Awaitable[T]]) -> T | None:
        started = time.perf_counter()
        try:
            result = await fn()
        except _Skipped as skipped:
            steps.append(StepRecord(name=name, status="skipped", duration_ms=0, detail=str(skipped)))
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("step_failed step=%s type=%s", name, type(exc).__name__)
            steps.append(StepRecord(name=name, status="failed", duration_ms=_ms(started), detail=type(exc).__name__))
            return None
        steps.append(StepRecord(name=name, status="completed", duration_ms=_ms(started)))
        return result

    @staticmethod
    def _cancel(*tasks: "asyncio.Task[Any]") -> None:
        for task in tasks:
            task.cancel()


class _Skipped(Exception):
    pass


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _empty_metadata() -> MetadataResult:
    return MetadataResult(
        any_metadata=False,
        exif_present=False,
        xmp_present=False,
        icc_profile_present=False,
        text_chunks_present=False,
        camera_make_model_present=False,
        groups=[],
        generator_signals=[],
        notes=["Metadata could not be read for this file. No conclusion is drawn from this."],
    )


def _failed_provenance() -> ProvenanceResult:
    return ProvenanceResult(
        status="unavailable",
        title="Content Credentials check did not run",
        summary="Provenance verification was disabled or failed for this analysis. No conclusion is drawn from this.",
        does_not_establish=["Whether the image has Content Credentials."],
    )


def _unavailable_forensics() -> ForensicsResult:
    return ForensicsResult(
        status="unavailable",
        signals=[],
        notes=["Visual forensic measurements were disabled or failed for this analysis."],
    )


def _evidence_sources(
    classification: Any,
    metadata: MetadataResult,
    provenance: ProvenanceResult,
    forensics: ForensicsResult,
    basis: str,
    steps: list[StepRecord],
) -> list[EvidenceSource]:
    step_status = {s.name: s.status for s in steps}

    if metadata.exif_present or metadata.xmp_present or metadata.text_chunks_present:
        meta_summary = "Embedded metadata was found and is shown separately."
        if metadata.generator_signals:
            meta_summary += " It includes text that names generation tooling (unauthenticated)."
        meta_status = "evaluated"
    elif step_status.get("metadata") == "failed":
        meta_summary, meta_status = "Metadata could not be read.", "failed"
    else:
        meta_summary, meta_status = "No EXIF, XMP or text metadata found. Absence is not evidence either way.", "not_found"

    prov_status_map = {
        "not_found": ("not_found", "No Content Credentials found."),
        "trusted": ("evaluated", "Content Credentials verified with a trusted signer."),
        "valid": ("evaluated", "Content Credentials intact; signer not confirmed as trusted."),
        "invalid": ("evaluated", "Content Credentials present but failed validation."),
        "error": ("failed", "Content Credentials could not be evaluated."),
        "unavailable": ("unavailable", "Provenance verification was not available."),
    }
    p_status, p_summary = prov_status_map[provenance.status]

    if forensics.status == "unavailable":
        f_status, f_summary = "unavailable", "Forensic measurements were not available."
    else:
        f_status, f_summary = "evaluated", "Noise, frequency and compression measurements are reported as informational context."

    return [
        EvidenceSource(
            id="classifier",
            label="Visual classifier",
            status="evaluated",
            used_in_classification=basis == "classifier",
            summary="A pretrained model scored the image's pixels. This determines the category unless verified provenance overrides it.",
        ),
        EvidenceSource(id="metadata", label="Metadata", status=meta_status, used_in_classification=False, summary=meta_summary),  # type: ignore[arg-type]
        EvidenceSource(
            id="provenance",
            label="Provenance (C2PA)",
            status=p_status,  # type: ignore[arg-type]
            used_in_classification=basis == "provenance",
            summary=p_summary,
        ),
        EvidenceSource(id="forensics", label="Visual forensics", status=f_status, used_in_classification=False, summary=f_summary),  # type: ignore[arg-type]
    ]


def _limitations(classification: Any) -> list[str]:
    calibrated = classification.interpretation.calibrated
    items = [
        "Results are estimates. No detector can guarantee the origin of every image.",
        "The classifier only knows the generators and photographs it was trained on. Newer generators, unusual image types and heavy post-processing can cause both missed detections and false alarms.",
        "Compression, resizing, cropping, filters and screenshots can remove or imitate the cues detectors rely on.",
        "AI-assisted editing (for example generative fill or retouching of a real photo) is not the same as AI generation, and whole-image classifiers are not designed to localise such edits.",
        "Missing metadata or missing Content Credentials is normal and is not evidence of AI generation.",
        "Embedded metadata and unsigned provenance claims can be forged or stripped.",
    ]
    if calibrated:
        items.append("The calibrated estimate is valid only for images that resemble the evaluation set it was fitted on.")
    else:
        items.append("The score is a raw model output, not a calibrated probability, and the thresholds have not been validated for this deployment.")
    return items
