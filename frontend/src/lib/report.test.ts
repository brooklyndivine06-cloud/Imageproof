import { describe, expect, it } from "vitest";

import { makeResult } from "@/test/fixtures";
import { buildReportPdf, pdfSafe, reportFileName } from "./report-pdf";
import { buildSummaryText } from "./summary";

describe("buildSummaryText", () => {
  it("includes the assessment, evidence, thresholds and disclaimer, but no metadata values", () => {
    const text = buildSummaryText(makeResult(), "photo.jpg");
    expect(text).toContain("Assessment: Likely AI-Generated");
    expect(text).toContain("uncalibrated model output, not a probability");
    expect(text).toContain("not validated");
    expect(text).toContain("Detection results are estimates");
    expect(text).not.toContain("TestCam");
  });
});

describe("PDF report", () => {
  it("produces a valid PDF containing the required sections", () => {
    const doc = buildReportPdf(makeResult(), { fileName: "photo.jpg" });
    const raw = doc.output();
    expect(raw.startsWith("%PDF-")).toBe(true);
    for (const text of ["Likely AI-Generated", "Evidence sources", "Detection model", "Limitations", "test/model", "Results are estimates"]) {
      expect(raw).toContain(text);
    }
    expect(doc.getNumberOfPages()).toBeGreaterThanOrEqual(1);
    expect(reportFileName(makeResult())).toBe("imageproof-report-123e4567.pdf");
  });

  it("survives characters outside Latin-1", () => {
    expect(pdfSafe("≤ 0.15 – “quoted” … 日本")).toBe('<= 0.15 - "quoted" ... ??');
    const r = makeResult();
    r.assessment.summary = "Unicode ≤ test 日本語";
    expect(() => buildReportPdf(r, { fileName: "日本.jpg" })).not.toThrow();
  });
});
