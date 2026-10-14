import { formatDateTime } from "./format";
import type { AnalysisResult } from "./types";

/** Plain-text summary for copying. Contains no image data and no metadata values. */
export function buildSummaryText(result: AnalysisResult, fileName: string): string {
  const a = result.assessment;
  const c = result.classification;
  const lines: string[] = [];
  lines.push("ImageProof analysis summary");
  lines.push(`File: ${fileName} (${result.file.format}, ${result.file.width}×${result.file.height} px)`);
  lines.push(`SHA-256: ${result.file.sha256}`);
  lines.push(`Analyzed: ${formatDateTime(result.created_at)} (analysis ${result.analysis_id})`);
  lines.push("");
  lines.push(`Assessment: ${a.label}`);
  lines.push(`Basis: ${a.basis === "provenance" ? "verified Content Credentials" : "visual classifier"}`);
  lines.push(a.summary);
  lines.push("");
  lines.push(
    `Classifier: ${c.model.name}${c.model.version ? ` (${c.model.version.slice(0, 12)})` : ""}, raw AI-label score ${c.ai_score.toFixed(3)}` +
      ` ${c.interpretation.calibrated ? "(calibrated estimate available)" : "(uncalibrated model output, not a probability)"}`,
  );
  lines.push(
    `Thresholds: camera ≤ ${c.thresholds.real.toFixed(2)}, AI ≥ ${c.thresholds.ai.toFixed(2)} (${c.thresholds.validated ? "evaluated" : "not validated"})`,
  );
  lines.push(`Reliability: ${a.reliability.level}`);
  for (const f of a.reliability.factors) lines.push(`  - ${f.message}`);
  lines.push("");
  lines.push("Evidence sources:");
  for (const e of result.evidence_sources) {
    lines.push(`  - ${e.label}: ${e.status.replace("_", " ")}${e.used_in_classification ? " (used for the assessment)" : ""}. ${e.summary}`);
  }
  lines.push(`Provenance: ${result.provenance.title}`);
  if (result.metadata.generator_signals.length) {
    lines.push(`Metadata signals: ${result.metadata.generator_signals.map((s) => s.source).join("; ")}`);
  }
  for (const note of a.notes) lines.push(`Note: ${note}`);
  lines.push("");
  lines.push(result.disclaimer);
  return lines.join("\n");
}
