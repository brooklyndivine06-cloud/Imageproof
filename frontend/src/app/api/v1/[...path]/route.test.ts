// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const ctx = (...path: string[]) => ({ params: Promise.resolve({ path }) });
afterEach(() => vi.unstubAllGlobals());

describe("API proxy", () => {
  it("only forwards the three public endpoints", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect((await GET(new NextRequest("http://x/api/v1/admin"), ctx("admin"))).status).toBe(404);
    expect((await GET(new NextRequest("http://x/api/v1/a/b"), ctx("a", "b"))).status).toBe(404);
    expect((await POST(new NextRequest("http://x/api/v1/status", { method: "POST" }), ctx("status"))).status).toBe(405);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("refuses oversized uploads before streaming them", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const req = new NextRequest("http://x/api/v1/analyze", { method: "POST", headers: { "content-length": String(50 * 1024 * 1024) }, body: "x" });
    const res = await POST(req, ctx("analyze"));
    expect(res.status).toBe(413);
    expect((await res.json()).error.code).toBe("file_too_large");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("passes status, selected headers and body through, and drops everything else", async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: 1 }), { status: 429, headers: { "content-type": "application/json", "retry-after": "30", "set-cookie": "a=b", server: "x" } }),
    );
    vi.stubGlobal("fetch", fetchSpy);
    const res = await GET(new NextRequest("http://x/api/v1/status", { headers: { cookie: "session=secret", authorization: "Bearer t", accept: "application/json" } }), ctx("status"));
    expect(res.status).toBe(429);
    expect(res.headers.get("retry-after")).toBe("30");
    expect(res.headers.get("set-cookie")).toBeNull();
    expect(res.headers.get("cache-control")).toBe("no-store");
    const [, init] = fetchSpy.mock.calls[0]!;
    const sent = init.headers as Headers;
    expect(sent.get("cookie")).toBeNull();
    expect(sent.get("authorization")).toBeNull();
    expect(sent.get("accept")).toBe("application/json");
  });

  it("reports an unreachable backend with a structured error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const res = await GET(new NextRequest("http://x/api/v1/status"), ctx("status"));
    expect(res.status).toBe(502);
    expect((await res.json()).error.code).toBe("backend_unreachable");
  });
});
