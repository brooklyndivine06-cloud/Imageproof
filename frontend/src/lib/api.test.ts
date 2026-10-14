import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { makeResult } from "@/test/fixtures";
import { analyzeImage, ApiError, describeError } from "./api";

class FakeXHR {
  static last: FakeXHR;
  upload: { onprogress?: (e: unknown) => void; onload?: () => void } = {};
  status = 0;
  responseText = "";
  timeout = 0;
  responseType = "";
  headers: Record<string, string> = {};
  responseHeaders: Record<string, string> = {};
  body: unknown;
  method = "";
  url = "";
  onload?: () => void;
  onerror?: () => void;
  ontimeout?: () => void;
  onabort?: () => void;
  constructor() {
    FakeXHR.last = this;
  }
  open(method: string, url: string) { this.method = method; this.url = url; }
  setRequestHeader(k: string, v: string) { this.headers[k] = v; }
  getResponseHeader(k: string) { return this.responseHeaders[k.toLowerCase()] ?? null; }
  send(body: unknown) { this.body = body; }
  abort() { this.onabort?.(); }
  respond(status: number, body: unknown, headers: Record<string, string> = {}) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.responseHeaders = headers;
    this.upload.onload?.();
    this.onload?.();
  }
}

const file = () => new File([new Uint8Array([0xff, 0xd8, 0xff])], "photo.jpg", { type: "image/jpeg" });

beforeEach(() => vi.stubGlobal("XMLHttpRequest", FakeXHR));
afterEach(() => vi.unstubAllGlobals());

describe("analyzeImage", () => {
  it("posts multipart form data with a 'file' field and reports real upload progress", async () => {
    const progress: number[] = [];
    const done = vi.fn();
    const p = analyzeImage(file(), { onUploadProgress: (f) => progress.push(f), onUploadComplete: done });
    const xhr = FakeXHR.last;
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/v1/analyze");
    expect(xhr.body).toBeInstanceOf(FormData);
    expect((xhr.body as FormData).get("file")).toBeInstanceOf(File);
    xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
    xhr.respond(200, makeResult());
    await expect(p).resolves.toMatchObject({ assessment: { category: "likely_ai_generated" } });
    expect(progress).toEqual([0.5]);
    expect(done).toHaveBeenCalled();
  });

  it("maps API error envelopes to ApiError", async () => {
    const p = analyzeImage(file());
    FakeXHR.last.respond(503, { error: { code: "model_not_configured", message: "No model", details: null, retryable: false }, request_id: "abc" });
    await expect(p).rejects.toMatchObject({ code: "model_not_configured", status: 503, requestId: "abc", retryable: false });
  });

  it("reads Retry-After on rate limiting", async () => {
    const p = analyzeImage(file());
    FakeXHR.last.respond(429, { error: { code: "rate_limited", message: "Slow down", details: null, retryable: true }, request_id: null }, { "retry-after": "120" });
    const err = (await p.catch((e) => e)) as ApiError;
    expect(err.retryAfterSeconds).toBe(120);
    expect(describeError(err).hint).toContain("2 min");
  });

  it("handles non-JSON errors, network failures, timeouts and aborts", async () => {
    let p = analyzeImage(file());
    FakeXHR.last.status = 502; FakeXHR.last.responseText = "<html>bad gateway</html>"; FakeXHR.last.onload?.();
    await expect(p).rejects.toMatchObject({ code: "server_error", retryable: true });

    p = analyzeImage(file());
    FakeXHR.last.onerror?.();
    await expect(p).rejects.toMatchObject({ code: "network_error" });

    p = analyzeImage(file());
    FakeXHR.last.ontimeout?.();
    await expect(p).rejects.toMatchObject({ code: "client_timeout" });

    const controller = new AbortController();
    p = analyzeImage(file(), { signal: controller.signal });
    controller.abort();
    await expect(p).rejects.toMatchObject({ name: "AbortError" });
  });

  it("rejects an unreadable success body", async () => {
    const p = analyzeImage(file());
    FakeXHR.last.status = 200; FakeXHR.last.responseText = "not json"; FakeXHR.last.onload?.();
    await expect(p).rejects.toMatchObject({ code: "invalid_response" });
  });
});

describe("describeError", () => {
  it("explains a missing model without inventing a result", () => {
    const info = describeError(new ApiError({ code: "model_not_configured", message: "x", status: 503 }));
    expect(info.title).toMatch(/not configured/i);
    expect(info.message).toMatch(/No result has been generated/);
    expect(info.canRetry).toBe(false);
  });
});
