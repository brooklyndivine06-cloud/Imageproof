import { jsPDF } from "jspdf";
import { autoTable } from "jspdf-autotable";

import { formatDateTime } from "./format";
import type { AnalysisResult } from "./types";

export interface ReportThumbnail {
  dataUrl: string; // JPEG
  width: number;
  height: number;
}

const MARGIN = 15;
const PAGE_W = 210;
const PAGE_H = 297;
const CONTENT_W = PAGE_W - MARGIN * 2;
const INK: [number, number, number] = [24, 32, 48];
const MUTED: [number, number, number] = [96, 106, 120];

/** The built-in PDF fonts only cover Latin-1, so map or drop anything outside it. */
export function pdfSafe(text: string): string {
  return text
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/\u2026/g, "...")
    .replace(/\u2264/g, "<=")
    .replace(/\u2265/g, ">=")
    .replace(/\u00a0/g, " ")
    .replace(/[^\x09\x0a\x0d\x20-\x7e\xa0-\xff]/g, "?");
}

type Doc = jsPDF & { lastAutoTable?: { finalY?: number } };

class Cursor {
  y = MARGIN;
  constructor(readonly doc: Doc) {}

  ensure(height: number) {
    if (this.y + height > PAGE_H - 18) {
      this.doc.addPage();
      this.y = MARGIN;
    }
  }

  heading(text: string) {
    this.ensure(14);
    this.y += 4;
    this.doc.setFont("helvetica", "bold").setFontSize(12).setTextColor(...INK);
    this.doc.text(pdfSafe(text), MARGIN, this.y);
    this.y += 2;
    this.doc.setDrawColor(210, 216, 224).line(MARGIN, this.y, PAGE_W - MARGIN, this.y);
    this.y += 5;
  }

  paragraph(text: string, opts: { size?: number; color?: [number, number, number]; bold?: boolean } = {}) {
    const size = opts.size ?? 9.5;
    this.doc.setFont("helvetica", opts.bold ? "bold" : "normal").setFontSize(size).setTextColor(...(opts.color ?? INK));
    const lines = this.doc.splitTextToSize(pdfSafe(text), CONTENT_W) as string[];
    const lineH = size * 0.42;
    for (const line of lines) {
      this.ensure(lineH + 1);
      this.doc.text(line, MARGIN, this.y);
      this.y += lineH + 0.9;
    }
    this.y += 1.5;
  }

  bullets(items: string[]) {
    for (const item of items) {
      this.doc.setFont("helvetica", "normal").setFontSize(9.5).setTextColor(...INK);
      const lines = this.doc.splitTextToSize(pdfSafe(item), CONTENT_W - 5) as string[];
      lines.forEach((line, i) => {
        this.ensure(5);
        if (i === 0) this.doc.text("-", MARGIN + 1, this.y);
        this.doc.text(line, MARGIN + 5, this.y);
        this.y += 4.6;
      });
      this.y += 0.8;
    }
    this.y += 1;
  }

  table(head: string[], body: string[][], widths?: number[]) {
    this.ensure(14);
    autoTable(this.doc, {
      startY: this.y,
      head: [head.map(pdfSafe)],
      body: body.map((r) => r.map(pdfSafe)),
      margin: { left: MARGIN, right: MARGIN, bottom: 18 },
      theme: "grid",
      styles: { font: "helvetica", fontSize: 8.5, cellPadding: 2, textColor: INK, lineColor: [220, 225, 232], lineWidth: 0.2, overflow: "linebreak" },
      headStyles: { fillColor: [238, 241, 245], textColor: INK, fontStyle: "bold" },
      columnStyles: widths ? Object.fromEntries(widths.map((w, i) => [i, { cellWidth: w }])) : undefined,
    });
    this.y = (this.doc.lastAutoTable?.finalY ?? this.y) + 5;
  }
}

export function buildReportPdf(result: AnalysisResult, opts: { fileName: string; thumbnail?: ReportThumbnail }): jsPDF {
  const doc: Doc = new jsPDF({ unit: "mm", format: "a4" });
  doc.setProperties({ title: `ImageProof report ${result.analysis_id}`, subject: "Image authenticity analysis", creator: "ImageProof" });
  const c = new Cursor(doc);
  const a = result.assessment;
  const cls = result.classification;

  // Title block
  doc.setFont("helvetica", "bold").setFontSize(20).setTextColor(...INK).text("ImageProof analysis report", MARGIN, c.y + 6);
  c.y += 12;
  doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(...MUTED);
  doc.text(pdfSafe(`Analysis ${result.analysis_id}  |  ${formatDateTime(result.created_at)}  |  ImageProof ${result.app_version}`), MARGIN, c.y);
  c.y += 7;

  // Disclaimer banner
  doc.setFillColor(246, 243, 232).rect(MARGIN, c.y - 3.5, CONTENT_W, 14, "F");
  doc.setFont("helvetica", "normal").setFontSize(8.5).setTextColor(...INK);
  const banner = doc.splitTextToSize(pdfSafe(result.disclaimer), CONTENT_W - 6) as string[];
  banner.slice(0, 3).forEach((line, i) => doc.text(line, MARGIN + 3, c.y + i * 4));
  c.y += 15;

  // Assessment
  c.heading("Assessment");
  doc.setFont("helvetica", "bold").setFontSize(16).setTextColor(...INK).text(pdfSafe(a.label), MARGIN, c.y + 1);
  c.y += 7;
  c.paragraph(`Basis: ${a.basis === "provenance" ? "verified Content Credentials from a trusted signer" : "visual classifier output"}. Reliability: ${a.reliability.level}.`, {
    color: MUTED,
    size: 9,
  });
  c.paragraph(a.summary);
  for (const note of a.notes) c.paragraph(`Note: ${note}`);
  if (a.reliability.factors.length) {
    c.paragraph("Reliability factors", { bold: true });
    c.bullets(a.reliability.factors.map((f) => f.message));
  }
  c.paragraph("How the assessment was reached", { bold: true });
  c.bullets(a.decision_trace);

  // File
  c.heading("Analyzed file");
  if (opts.thumbnail) {
    const maxW = 55;
    const maxH = 45;
    const ratio = Math.min(maxW / opts.thumbnail.width, maxH / opts.thumbnail.height);
    const w = opts.thumbnail.width * ratio;
    const h = opts.thumbnail.height * ratio;
    c.ensure(h + 4);
    doc.addImage(opts.thumbnail.dataUrl, "JPEG", MARGIN, c.y, w, h);
    doc.setDrawColor(210, 216, 224).rect(MARGIN, c.y, w, h);
    const x = MARGIN + w + 6;
    doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(...INK);
    const lines = [
      `File name: ${opts.fileName}`,
      `Format: ${result.file.format} (detected from content)`,
      `Dimensions: ${result.file.width} x ${result.file.height} px (${result.file.megapixels} MP)`,
      `Size: ${(result.file.size_bytes / 1024).toFixed(0)} KB`,
      `SHA-256:`,
      result.file.sha256.slice(0, 32),
      result.file.sha256.slice(32),
    ];
    lines.forEach((l, i) => doc.text(pdfSafe(l), x, c.y + 5 + i * 5));
    c.y += Math.max(h, 40) + 4;
  } else {
    c.table(["Property", "Value"], [
      ["File name", opts.fileName],
      ["Format", `${result.file.format} (detected from content)`],
      ["Dimensions", `${result.file.width} x ${result.file.height} px (${result.file.megapixels} MP)`],
      ["Size", `${(result.file.size_bytes / 1024).toFixed(0)} KB`],
      ["SHA-256", result.file.sha256],
    ], [40, CONTENT_W - 40]);
  }

  // Classification
  c.heading("Classifier output");
  c.table(["Label", "Role", "Raw score"], cls.labels.map((l) => [l.label, l.role === "ai_generated" ? "AI-generated" : l.role === "camera" ? "Real / camera" : "Other", l.score.toFixed(4)]), [70, 60, CONTENT_W - 130]);
  c.paragraph(
    `AI-label score: ${cls.ai_score.toFixed(4)}. Thresholds: Likely Camera-Captured at or below ${cls.thresholds.real.toFixed(2)}; Likely AI-Generated at or above ${cls.thresholds.ai.toFixed(2)} (${cls.thresholds.validated ? "evaluated on a labelled dataset" : "configured, not validated"}).`,
  );
  c.paragraph(cls.interpretation.description, { color: MUTED, size: 9 });
  if (cls.interpretation.calibration?.calibrated_ai_probability != null) {
    const cal = cls.interpretation.calibration;
    c.paragraph(`Calibrated estimate: ${((cal.calibrated_ai_probability ?? 0) * 100).toFixed(0)}% (fitted on ${cal.fitted_on}). Valid only for similar images.`);
  }

  // Evidence
  c.heading("Evidence sources");
  c.table(
    ["Source", "Status", "Used for assessment", "Summary"],
    result.evidence_sources.map((e) => [e.label, e.status.replace("_", " "), e.used_in_classification ? "Yes" : "No (context)", e.summary]),
    [32, 24, 28, CONTENT_W - 84],
  );

  // Metadata
  c.heading("Metadata");
  for (const n of result.metadata.notes) c.paragraph(n, { color: MUTED, size: 9 });
  for (const g of result.metadata.groups) {
    c.table([g.label, "Value"], g.fields.map((f) => [f.label, f.value]), [60, CONTENT_W - 60]);
  }
  if (result.metadata.generator_signals.length) {
    c.paragraph("Generator-related signals (unauthenticated)", { bold: true });
    c.bullets(result.metadata.generator_signals.map((s) => `${s.source}: ${s.description}${s.excerpt ? ` [${s.excerpt}]` : ""}`));
  }

  // Provenance
  const p = result.provenance;
  c.heading("Provenance (C2PA Content Credentials)");
  c.paragraph(p.title, { bold: true });
  c.paragraph(p.summary);
  const prow: string[][] = [];
  if (p.validation_state) prow.push(["Validation state", p.validation_state]);
  if (p.signer) prow.push(["Signer", p.signer]);
  if (p.signed_at) prow.push(["Signed", p.signed_at]);
  if (p.claim_generator) prow.push(["Claim generator", p.claim_generator]);
  if (prow.length) c.table(["Property", "Value"], prow, [45, CONTENT_W - 45]);
  if (p.actions.length) {
    c.table(["Action", "Software", "Source type"], p.actions.map((x) => [x.action, x.software_agent ?? "-", x.digital_source_type ?? "-"]), [55, 60, CONTENT_W - 115]);
  }
  if (p.issues.length) c.bullets(p.issues.map((i) => `${i.code}${i.explanation ? `: ${i.explanation}` : ""}`));
  if (p.does_not_establish.length) {
    c.paragraph("This does not establish:", { bold: true });
    c.bullets(p.does_not_establish);
  }

  // Forensics
  c.heading("Visual forensics (informational, not used for the assessment)");
  if (result.forensics.signals.length) {
    c.table(["Measurement", "Value", "What it means"], result.forensics.signals.map((s) => [s.label, `${s.value ?? "n/a"} ${s.unit ?? ""}`.trim(), s.interpretation]), [42, 32, CONTENT_W - 74]);
  }
  for (const n of result.forensics.notes) c.paragraph(n, { color: MUTED, size: 9 });

  // Model
  c.heading("Detection model");
  c.table(["Property", "Value"], [
    ["Model", cls.model.name],
    ["Version / revision", cls.model.version ?? "not reported"],
    ["Provider", cls.model.provider],
    ["License", cls.model.license ?? "not stated"],
    ["Data handling", cls.model.data_handling],
    ["Processing time", `${result.processing.duration_ms} ms`],
  ], [45, CONTENT_W - 45]);

  // Limitations
  c.heading("Limitations");
  c.bullets(result.limitations);
  c.paragraph(result.disclaimer, { bold: true });

  // Footer on every page
  const pages = doc.getNumberOfPages();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(...MUTED);
    doc.text(pdfSafe(`ImageProof report ${result.analysis_id.slice(0, 8)}  |  Estimates, not proof of authenticity`), MARGIN, PAGE_H - 8);
    doc.text(`Page ${i} of ${pages}`, PAGE_W - MARGIN, PAGE_H - 8, { align: "right" });
  }
  return doc;
}

export function reportFileName(result: AnalysisResult): string {
  return `imageproof-report-${result.analysis_id.slice(0, 8)}.pdf`;
}
