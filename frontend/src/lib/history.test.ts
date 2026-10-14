import { beforeEach, describe, expect, it } from "vitest";

import { makeResult } from "@/test/fixtures";
import { clearHistory, getSnapshot, recordAnalysis, removeEntry, setConsent } from "./history";

beforeEach(() => {
  window.localStorage.clear();
  setConsent(false);
});

describe("history", () => {
  it("saves nothing without explicit consent", () => {
    expect(recordAnalysis(makeResult(), "a.jpg")).toBe(false);
    expect(getSnapshot().entries).toHaveLength(0);
    expect(window.localStorage.getItem("imageproof.history.v1")).toBeNull();
  });

  it("stores only a small summary after consent, never image or metadata data", () => {
    setConsent(true);
    expect(recordAnalysis(makeResult(), "a.jpg")).toBe(true);
    const [entry] = getSnapshot().entries;
    expect(entry).toMatchObject({ fileName: "a.jpg", category: "likely_ai_generated", aiScore: 0.93 });
    const stored = window.localStorage.getItem("imageproof.history.v1")!;
    expect(stored).not.toContain("TestCam");
    expect(stored).not.toContain("data:image");
  });

  it("removes entries and deletes everything when consent is withdrawn", () => {
    setConsent(true);
    recordAnalysis(makeResult(), "a.jpg");
    removeEntry(getSnapshot().entries[0]!.id);
    expect(getSnapshot().entries).toHaveLength(0);
    recordAnalysis(makeResult(), "b.jpg");
    clearHistory();
    expect(getSnapshot().entries).toHaveLength(0);
    recordAnalysis(makeResult(), "c.jpg");
    setConsent(false);
    expect(window.localStorage.getItem("imageproof.history.v1")).toBeNull();
    expect(getSnapshot().consent).toBe(false);
  });
});
