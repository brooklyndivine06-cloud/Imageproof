/** Mirrors the JSON contract of POST /api/v1/analyze and GET /api/v1/status. */

export type Category = "likely_ai_generated" | "likely_camera_captured" | "inconclusive" | "unable_to_analyze";

export interface StepRecord {
  name: string;
  status: "completed" | "skipped" | "unavailable" | "failed";
  duration_ms: number;
  detail: string | null;
}

export interface FileInfo {
  format: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  megapixels: number;
  color_mode: string;
  sha256: string;
}

export interface ModelInfo {
  provider: string;
  name: string;
  version: string | null;
  task: string;
  external: boolean;
  data_handling: string;
  license: string | null;
  description: string | null;
}

export interface LabelScore {
  label: string;
  score: number;
  role: "ai_generated" | "camera" | "other";
}

export interface CalibrationInfo {
  method: string;
  fitted_on: string;
  n_real: number | null;
  n_ai: number | null;
  created_at: string | null;
  calibrated_ai_probability: number | null;
}

export interface ScoreInterpretation {
  score_type: "raw_softmax" | "calibrated_probability";
  calibrated: boolean;
  description: string;
  calibration: CalibrationInfo | null;
}

export interface Thresholds {
  ai: number;
  real: number;
  source: "configured" | "evaluation";
  validated: boolean;
  description: string;
}

export interface ClassificationResult {
  status: "completed";
  model: ModelInfo;
  ai_score: number;
  labels: LabelScore[];
  interpretation: ScoreInterpretation;
  thresholds: Thresholds;
  decision: "ai" | "camera" | "between";
}

export interface MetadataField {
  key: string;
  label: string;
  value: string;
}
export interface MetadataGroup {
  id: string;
  label: string;
  fields: MetadataField[];
}
export interface GeneratorSignal {
  source: string;
  kind: "generation_parameters" | "software_string" | "declared_digital_source_type";
  description: string;
  excerpt: string | null;
}
export interface MetadataResult {
  any_metadata: boolean;
  exif_present: boolean;
  xmp_present: boolean;
  icc_profile_present: boolean;
  text_chunks_present: boolean;
  camera_make_model_present: boolean;
  groups: MetadataGroup[];
  generator_signals: GeneratorSignal[];
  withheld: string[];
  other_tag_names: string[];
  notes: string[];
}

export interface ProvenanceAction {
  action: string;
  software_agent: string | null;
  digital_source_type: string | null;
  description: string | null;
}
export interface ValidationIssue {
  code: string;
  explanation: string | null;
}
export interface ProvenanceResult {
  status: "not_found" | "valid" | "trusted" | "invalid" | "unavailable" | "error";
  validation_state: string | null;
  title: string;
  summary: string;
  signer: string | null;
  signed_at: string | null;
  claim_generator: string | null;
  actions: ProvenanceAction[];
  ingredients_count: number;
  declares_ai_generation: boolean;
  declares_partial_ai: boolean;
  declares_camera_capture: boolean;
  issues: ValidationIssue[];
  establishes: string[];
  does_not_establish: string[];
  library: string | null;
}

export interface ForensicSignal {
  id: string;
  label: string;
  value: number | string | null;
  unit: string | null;
  interpretation: string;
}
export interface ElaResult {
  applicable: boolean;
  reason: string | null;
  mean: number | null;
  p99: number | null;
  heatmap_data_url: string | null;
  note: string | null;
}
export interface ForensicsResult {
  status: "completed" | "partial" | "unavailable";
  signals: ForensicSignal[];
  ela: ElaResult | null;
  notes: string[];
  used_in_classification: boolean;
  region: string | null;
}

export interface ReliabilityFactor {
  code: string;
  severity: "info" | "caution" | "limiting";
  message: string;
}
export interface Reliability {
  level: "standard" | "reduced" | "low";
  factors: ReliabilityFactor[];
}
export interface Assessment {
  category: Category;
  label: string;
  basis: "classifier" | "provenance";
  headline: string;
  summary: string;
  decision_trace: string[];
  reliability: Reliability;
  notes: string[];
}
export interface EvidenceSource {
  id: "classifier" | "metadata" | "provenance" | "forensics";
  label: string;
  status: "evaluated" | "not_found" | "not_applicable" | "unavailable" | "failed";
  used_in_classification: boolean;
  summary: string;
}

export interface AnalysisResult {
  analysis_id: string;
  created_at: string;
  app_version: string;
  processing: { status: "completed"; duration_ms: number; steps: StepRecord[] };
  file: FileInfo;
  assessment: Assessment;
  classification: ClassificationResult;
  evidence_sources: EvidenceSource[];
  metadata: MetadataResult;
  provenance: ProvenanceResult;
  forensics: ForensicsResult;
  limitations: string[];
  disclaimer: string;
}

export interface Rate {
  k: number;
  n: number;
  rate: number | null;
  ci95: [number, number] | null;
}
export interface OverallMetrics {
  n_real: number;
  n_ai: number;
  auroc: number | null;
  false_positive_rate: Rate;
  recall_ai: Rate;
  precision_ai: Rate;
  inconclusive_rate_real: Rate;
  inconclusive_rate_ai: Rate;
  ai_called_camera_rate: Rate;
}
export interface SetMetrics {
  n: number;
  flagged_ai: Rate;
  flagged_camera: Rate;
  inconclusive: Rate;
}
export type EvaluationSummary =
  | { status: "none" | "model_mismatch"; message: string }
  | {
      status: "available";
      generated_at: string;
      dataset: {
        name: string;
        notes: string;
        sets: Record<string, { ground_truth: "real" | "ai"; images: number }>;
        evaluated_on: string;
        undecodable_files_skipped: number;
      };
      thresholds_used: { ai: number; real: number; fitted: boolean };
      overall: Record<string, OverallMetrics>;
      by_set: Record<string, { truth: "real" | "ai" } & Record<string, SetMetrics | string>>;
      limitations: string[];
    };

export interface ServiceStatus {
  service: string;
  version: string;
  ready: boolean;
  classifier: {
    state: "ready" | "loading" | "not_configured" | "error";
    detail: string | null;
    model: ModelInfo | null;
    thresholds: Thresholds;
    calibrated: boolean;
  };
  limits: {
    max_upload_bytes: number;
    max_upload_mb: number;
    min_side_px: number;
    max_pixels: number;
    formats: string[];
    mime_types: string[];
    rate_limit: { requests: number; window_seconds: number };
    timeout_seconds: number;
  };
  evidence_modules: {
    provenance: { enabled: boolean; available: boolean; library: string | null; reason: string | null };
    forensics: { enabled: boolean };
  };
  evaluation: EvaluationSummary;
  privacy: { stores_uploads: boolean; external_provider: boolean; data_handling: string; retention: string };
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> | null; retryable: boolean };
  request_id: string | null;
}
