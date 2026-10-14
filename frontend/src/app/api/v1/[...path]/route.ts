import type { NextRequest } from "next/server";

/**
 * Same-origin proxy to the FastAPI backend.
 *
 * - The browser only ever talks to this origin: no CORS configuration, and the backend address and any
 *   credentials stay on the server (BACKEND_URL is read at request time and is never sent to the client).
 * - Only the three public endpoints are forwarded.
 * - Upload bodies are streamed through, never buffered or written to disk here.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
const UPSTREAM_TIMEOUT_MS = 95_000;

// Keep in sync with IMAGEPROOF_MAX_UPLOAD_MB on the backend. The proxy refuses oversized bodies up front, because the
// backend closes the connection as soon as it sees an oversized Content-Length while this proxy would still be streaming.
const MAX_UPLOAD_MB = Number(process.env.MAX_UPLOAD_MB ?? "10");
const MAX_BODY_BYTES = (MAX_UPLOAD_MB + 1) * 1024 * 1024; // + multipart framing allowance

const ROUTES: Record<string, string> = { analyze: "POST", status: "GET", health: "GET" };
const FORWARD_REQUEST_HEADERS = ["content-type", "content-length", "accept", "x-forwarded-for"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "retry-after", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining"];

function errorResponse(status: number, code: string, message: string, retryable = false) {
  return Response.json(
    { error: { code, message, details: null, retryable }, request_id: null },
    { status, headers: { "cache-control": "no-store" } },
  );
}

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const name = path.length === 1 ? path[0] : undefined;
  const expectedMethod = name ? ROUTES[name] : undefined;
  if (!name || !expectedMethod) return errorResponse(404, "not_found", "Resource not found.");
  if (req.method !== expectedMethod) return errorResponse(405, "method_not_allowed", "Method not allowed.");

  if (req.method === "POST") {
    const declared = Number(req.headers.get("content-length") ?? "0");
    if (declared > MAX_BODY_BYTES) {
      return errorResponse(413, "file_too_large", `The upload exceeds the maximum size of about ${MAX_UPLOAD_MB} MB.`);
    }
  }

  const headers = new Headers();
  for (const key of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(key);
    if (value) headers.set(key, value);
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: req.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  };
  if (req.method === "POST") {
    init.body = req.body;
    init.duplex = "half";
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/${name}`, init);
  } catch (err) {
    const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
    return timedOut
      ? errorResponse(504, "analysis_timeout", "The analysis took too long and was stopped.", true)
      : errorResponse(502, "backend_unreachable", "The analysis backend could not be reached.", true);
  }

  const out = new Headers({ "cache-control": "no-store" });
  for (const key of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(key);
    if (value) out.set(key, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { handle as GET, handle as POST };
