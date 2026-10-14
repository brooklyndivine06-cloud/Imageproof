"""Public response models. These define the JSON contract of the API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Category = Literal["likely_ai_generated", "likely_camera_captured", "inconclusive", "unable_to_analyze"]

CATEGORY_LABELS: dict[str, str] = {
    "likely_ai_generated": "Likely AI-Generated",
    "likely_camera_captured": "Likely Camera-Captured",
    "inconclusive": "Inconclusive",
    "unable_to_analyze": "Unable to Analyze",
}


# --- Processing ---------------------------------------------------------------
class StepRecord(BaseModel):
    name: str
    status: Literal["completed", "skipped", "unavailable", "failed"]
    duration_ms: int
    detail: str | None = None


class ProcessingInfo(BaseModel):
    status: Literal["completed"] = "completed"
    duration_ms: int
    steps: list[StepRecord]


class FileInfo(BaseModel):
    format: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    megapixels: float
    color_mode: str
    sha256: str


# --- Classification -------------------------------------------------------------
class ModelInfo(BaseModel):
    provider: str
    name: str
    version: str | None = None
    task: str = "Binary image classification (AI-generated vs. real)"
    external: bool = False
    data_handling: str
    license: str | None = None
    description: str | None = None


class LabelScore(BaseModel):
    label: str
    score: float
    role: Literal["ai_generated", "camera", "other"]


class CalibrationInfo(BaseModel):
    method: str
    fitted_on: str
    n_real: int | None = None
    n_ai: int | None = None
    created_at: str | None = None
    calibrated_ai_probability: float | None = None


class ScoreInterpretation(BaseModel):
    score_type: Literal["raw_softmax", "calibrated_probability"]
    calibrated: bool
    description: str
    calibration: CalibrationInfo | None = None


class Thresholds(BaseModel):
    ai: float
    real: float
    source: Literal["configured", "evaluation"]
    validated: bool
    description: str


class ClassificationResult(BaseModel):
    status: Literal["completed"] = "completed"
    model: ModelInfo
    ai_score: float
    labels: list[LabelScore]
    interpretation: ScoreInterpretation
    thresholds: Thresholds
    decision: Literal["ai", "camera", "between"]


# --- Metadata -------------------------------------------------------------------
class MetadataField(BaseModel):
    key: str
    label: str
    value: str


class MetadataGroup(BaseModel):
    id: str
    label: str
    fields: list[MetadataField]


class GeneratorSignal(BaseModel):
    source: str
    kind: Literal["generation_parameters", "software_string", "declared_digital_source_type"]
    description: str
    excerpt: str | None = None


class MetadataResult(BaseModel):
    any_metadata: bool
    exif_present: bool
    xmp_present: bool
    icc_profile_present: bool
    text_chunks_present: bool
    camera_make_model_present: bool
    groups: list[MetadataGroup]
    generator_signals: list[GeneratorSignal]
    withheld: list[str] = Field(
        default_factory=list,
        description="Categories that were present but are intentionally not returned (e.g. GPS).",
    )
    other_tag_names: list[str] = Field(default_factory=list)
    notes: list[str]


# --- Provenance -------------------------------------------------------------------
class ProvenanceAction(BaseModel):
    action: str
    software_agent: str | None = None
    digital_source_type: str | None = None
    description: str | None = None


class ValidationIssue(BaseModel):
    code: str
    explanation: str | None = None


class ProvenanceResult(BaseModel):
    status: Literal["not_found", "valid", "trusted", "invalid", "unavailable", "error"]
    validation_state: str | None = None
    title: str
    summary: str
    signer: str | None = None
    signed_at: str | None = None
    claim_generator: str | None = None
    actions: list[ProvenanceAction] = Field(default_factory=list)
    ingredients_count: int = 0
    declares_ai_generation: bool = False
    declares_partial_ai: bool = False
    declares_camera_capture: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)
    establishes: list[str] = Field(default_factory=list)
    does_not_establish: list[str] = Field(default_factory=list)
    library: str | None = None


# --- Forensics --------------------------------------------------------------------
class ForensicSignal(BaseModel):
    id: str
    label: str
    value: float | int | str | None
    unit: str | None = None
    interpretation: str


class ElaResult(BaseModel):
    applicable: bool
    reason: str | None = None
    mean: float | None = None
    p99: float | None = None
    heatmap_data_url: str | None = None
    note: str | None = None


class ForensicsResult(BaseModel):
    status: Literal["completed", "partial", "unavailable"]
    signals: list[ForensicSignal]
    ela: ElaResult | None = None
    notes: list[str]
    used_in_classification: bool = False
    region: str | None = None


# --- Assessment -------------------------------------------------------------------
class ReliabilityFactor(BaseModel):
    code: str
    severity: Literal["info", "caution", "limiting"]
    message: str


class Reliability(BaseModel):
    level: Literal["standard", "reduced", "low"]
    factors: list[ReliabilityFactor]


class Assessment(BaseModel):
    category: Category
    label: str
    basis: Literal["classifier", "provenance"]
    headline: str
    summary: str
    decision_trace: list[str]
    reliability: Reliability
    notes: list[str]


class EvidenceSource(BaseModel):
    id: Literal["classifier", "metadata", "provenance", "forensics"]
    label: str
    status: Literal["evaluated", "not_found", "not_applicable", "unavailable", "failed"]
    used_in_classification: bool
    summary: str


class AnalysisResponse(BaseModel):
    analysis_id: str
    created_at: str
    app_version: str
    processing: ProcessingInfo
    file: FileInfo
    assessment: Assessment
    classification: ClassificationResult
    evidence_sources: list[EvidenceSource]
    metadata: MetadataResult
    provenance: ProvenanceResult
    forensics: ForensicsResult
    limitations: list[str]
    disclaimer: str


# --- Errors (documentation model) --------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
