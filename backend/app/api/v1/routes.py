from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import APP_VERSION, SUPPORTED_FORMATS
from app.core.errors import AppError
from app.core.rate_limit import client_ip
from app.schemas import AnalysisResponse, ErrorResponse
from app.services.provenance import provenance_library_info

logger = logging.getLogger("imageproof")
router = APIRouter(prefix="/api/v1")

_ANALYZE_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {"file": {"type": "string", "format": "binary", "description": "JPEG, PNG or WebP image"}},
                }
            }
        },
    }
}


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status", summary="Readiness, limits and model information")
async def status(request: Request) -> dict[str, Any]:
    state = request.app.state
    s = state.settings
    classifier_status = state.classifier.status()
    model = state.classifier.model_info()
    thresholds = state.analysis.thresholds_preview()
    ready = classifier_status.state == "ready"
    return {
        "service": "imageproof-api",
        "version": APP_VERSION,
        "ready": ready,
        "classifier": {
            "state": classifier_status.state,
            "detail": classifier_status.detail,
            "model": model.model_dump() if classifier_status.state != "not_configured" else None,
            "thresholds": thresholds.model_dump(),
            "calibrated": state.calibration is not None,
        },
        "limits": {
            "max_upload_bytes": s.max_upload_bytes,
            "max_upload_mb": s.max_upload_mb,
            "min_side_px": s.min_image_side,
            "max_pixels": s.max_image_pixels,
            "formats": list(SUPPORTED_FORMATS),
            "mime_types": list(SUPPORTED_FORMATS.values()),
            "rate_limit": {"requests": s.rate_limit_requests, "window_seconds": s.rate_limit_window_seconds},
            "timeout_seconds": s.analysis_timeout_seconds,
        },
        "evidence_modules": {
            "provenance": {"enabled": s.enable_provenance, **provenance_library_info()},
            "forensics": {"enabled": s.enable_forensics},
        },
        "evaluation": state.evaluation,
        "privacy": {
            "stores_uploads": False,
            "external_provider": model.external,
            "data_handling": model.data_handling,
            "retention": "Uploads are processed in memory and discarded when the response is sent. Image content, file names and metadata are not logged.",
        },
    }


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    summary="Analyze an uploaded image",
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
    openapi_extra=_ANALYZE_OPENAPI,
)
async def analyze(request: Request) -> AnalysisResponse:
    state = request.app.state
    s = state.settings

    # 1. Gate before reading the body: rate limit and readiness.
    decision = state.rate_limiter.hit(client_ip(request, s.trusted_proxy_count))
    if not decision.allowed:
        raise AppError(
            429,
            "rate_limited",
            "Too many analysis requests. Please wait before trying again.",
            retryable=True,
            details={"retry_after_seconds": decision.retry_after_seconds},
            headers={
                "Retry-After": str(decision.retry_after_seconds),
                "X-RateLimit-Limit": str(decision.limit),
                "X-RateLimit-Remaining": "0",
            },
        )

    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise AppError(415, "expected_multipart", "Send the image as multipart/form-data in a field named 'file'.")

    # 2. Parse the multipart body (kept in memory; the size cap is enforced in middleware).
    try:
        form = await request.form(max_files=1, max_fields=4)
    except StarletteHTTPException:
        raise AppError(400, "malformed_request", "The multipart request could not be parsed.") from None

    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise AppError(400, "missing_file", "No file was uploaded. Send the image in a form field named 'file'.")
    try:
        data = await upload.read(s.max_upload_bytes + 1)
    finally:
        await form.close()

    # 3. Analyze.
    result = await state.analysis.analyze(data)
    request.state.rate_limit_remaining = decision.remaining
    return result
