import type { AnalysisResult, ApiErrorBody, ServiceStatus } from "./types";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(opts: {
    code: string;
    message: string;
    status?: number;
    retryable?: boolean;
    requestId?: string | null;
    retryAfterSeconds?: number | null;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.code = opts.code;
    this.status = opts.status ?? 0;
    this.retryable = opts.retryable ?? false;
    this.requestId = opts.requestId ?? null;
    this.retryAfterSeconds = opts.retryAfterSeconds ?? null;
  }
}

const API_BASE = "/api/v1";
const CLIENT_TIMEOUT_MS = 120_000;

function parseErrorBody(status: number, text: string, retryAfterHeader: string | null): ApiError {
  const retryAfter = retryAfterHeader && /^\d+$/.test(retryAfterHeader) ? Number(retryAfterHeader) : null;
  try {
    const body = JSON.parse(text) as Partial<ApiErrorBody>;
    if (body.error?.code) {
      return new ApiError({
        code: body.error.code,
        message: body.error.message ?? "The request failed.",
        status,
        retryable: Boolean(body.error.retryable),
        requestId: body.request_id ?? null,
        retryAfterSeconds: retryAfter,
      });
    }
  } catch {
    /* not JSON: fall through */
  }
  return new ApiError({
    code: status >= 500 ? "server_error" : "request_failed",
    message: status >= 500 ? "The analysis service returned an unexpected error." : "The request could not be completed.",
    status,
    retryable: status >= 500,
    retryAfterSeconds: retryAfter,
  });
}

export async function fetchStatus(signal?: AbortSignal): Promise<ServiceStatus> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/status`, { signal, cache: "no-store" });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError({ code: "network_error", message: "Could not reach the analysis service.", retryable: true });
  }
  if (!res.ok) throw parseErrorBody(res.status, await res.text(), res.headers.get("retry-after"));
  return (await res.json()) as ServiceStatus;
}

export interface AnalyzeOptions {
  onUploadProgress?: (fraction: number) => void;
  onUploadComplete?: () => void;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** Uploads the image with XMLHttpRequest so real upload progress can be reported. */
export function analyzeImage(file: File, opts: AnalyzeOptions = {}): Promise<AnalysisResult> {
  return new Promise<AnalysisResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/analyze`);
    xhr.timeout = opts.timeoutMs ?? CLIENT_TIMEOUT_MS;
    xhr.responseType = "text";
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) opts.onUploadProgress?.(event.loaded / event.total);
    };
    xhr.upload.onload = () => opts.onUploadComplete?.();

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as AnalysisResult);
        } catch {
          reject(new ApiError({ code: "invalid_response", message: "The analysis service returned an unreadable response.", status: xhr.status }));
        }
        return;
      }
      reject(parseErrorBody(xhr.status, xhr.responseText, xhr.getResponseHeader("retry-after")));
    };
    xhr.onerror = () =>
      reject(new ApiError({ code: "network_error", message: "The connection to the analysis service failed.", retryable: true }));
    xhr.ontimeout = () =>
      reject(new ApiError({ code: "client_timeout", message: "The analysis took too long to respond.", retryable: true }));
    xhr.onabort = () => reject(new DOMException("Analysis cancelled", "AbortError"));

    if (opts.signal) {
      if (opts.signal.aborted) {
        xhr.abort();
        return;
      }
      opts.signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    const body = new FormData();
    body.append("file", file, file.name);
    xhr.send(body);
  });
}

export interface ErrorPresentation {
  title: string;
  message: string;
  hint: string | null;
  canRetry: boolean;
}

/** Turns an API error into plain-language guidance. These are the "Unable to Analyze" states. */
export function describeError(err: ApiError): ErrorPresentation {
  switch (err.code) {
    case "model_not_configured":
      return {
        title: "Detection model not configured",
        message: "This ImageProof server has no detection model enabled, so it cannot assess images. No result has been generated.",
        hint: "An administrator needs to configure a model provider (see the README, “Model configuration”).",
        canRetry: false,
      };
    case "model_loading":
      return {
        title: "The detection model is starting up",
        message: "The model is still loading on the server.",
        hint: "Wait a moment and try again.",
        canRetry: true,
      };
    case "model_unavailable":
    case "model_misconfigured":
      return {
        title: "Detection service unavailable",
        message: "The detection model could not be reached or is misconfigured. No result has been generated.",
        hint: err.retryable ? "Try again shortly." : "Contact the administrator of this deployment.",
        canRetry: err.retryable,
      };
    case "analysis_failed":
      return { title: "The analysis failed", message: err.message, hint: "Try again. If it keeps failing, try a different file.", canRetry: true };
    case "analysis_timeout":
    case "client_timeout":
      return { title: "The analysis timed out", message: "The server took too long to analyze this image.", hint: "Try a smaller image.", canRetry: true };
    case "rate_limited":
      return {
        title: "Too many requests",
        message: "You have reached the request limit for now.",
        hint: err.retryAfterSeconds ? `Try again in about ${Math.ceil(err.retryAfterSeconds / 60)} min.` : "Wait a few minutes and try again.",
        canRetry: true,
      };
    case "server_busy":
      return { title: "The server is busy", message: "Other analyses are running.", hint: "Try again in a few seconds.", canRetry: true };
    case "file_too_large":
      return { title: "File too large", message: err.message, hint: "Upload a smaller image.", canRetry: false };
    case "unsupported_media_type":
      return { title: "Unsupported file", message: err.message, hint: "Use a JPG, PNG or WebP image.", canRetry: false };
    case "corrupt_image":
      return { title: "The image could not be read", message: err.message, hint: "Export the image again from its source and upload the new file.", canRetry: false };
    case "image_too_small":
    case "image_too_large_dimensions":
    case "animated_not_supported":
    case "empty_file":
      return { title: "This image can’t be analyzed", message: err.message, hint: null, canRetry: false };
    case "network_error":
      return { title: "Connection problem", message: "The analysis service could not be reached.", hint: "Check your connection and try again.", canRetry: true };
    case "backend_unreachable":
      return { title: "Analysis service offline", message: "The ImageProof server could not reach its analysis backend.", hint: "Try again shortly or contact the administrator.", canRetry: true };
    default:
      return { title: "Something went wrong", message: err.message || "The analysis could not be completed.", hint: null, canRetry: err.retryable };
  }
}
