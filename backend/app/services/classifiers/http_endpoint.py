"""Hosted inference endpoint provider.

Posts the image to an HTTPS endpoint you control or subscribe to and expects a
JSON list of ``{"label": str, "score": float}`` objects, the response format of
Hugging Face image-classification inference endpoints. For a provider with a
different response format, copy this file, change ``_parse`` and register it
under a new name.

PRIVACY: this provider sends the uploaded image to a third-party server. The
status endpoint, the results page and the privacy page disclose this. By
default only decoded pixels are sent (re-encoded as lossless PNG), so EXIF,
GPS and other embedded metadata do not leave this server.
"""

from __future__ import annotations

import io
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.schemas import ModelInfo
from app.services.classifiers.base import (
    ClassifierFailure,
    ClassifierInput,
    ClassifierStatus,
    ClassifierUnavailable,
    ImageClassifier,
    LabelProbability,
)
from app.services.classifiers.registry import register_provider

logger = logging.getLogger("imageproof")

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class HttpEndpointClassifier(ImageClassifier):
    provider_id = "http_endpoint"

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._host = urlparse(settings.http_url).hostname if settings.http_url else None

        problem: str | None = None
        if not settings.http_url:
            self._status = ClassifierStatus("not_configured", "IMAGEPROOF_HTTP_URL is not set.")
        else:
            parsed = urlparse(settings.http_url)
            if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS):
                problem = "IMAGEPROOF_HTTP_URL must use https:// (plain http is only allowed for localhost)."
            if problem:
                self._status = ClassifierStatus("error", problem)
            else:
                self._status = ClassifierStatus("ready", None)

    async def startup(self) -> None:
        if self._status.state == "ready":
            s = self._settings
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(s.http_timeout_seconds, connect=min(10.0, s.http_timeout_seconds)),
                transport=self._transport,
                follow_redirects=False,
            )

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()

    def status(self) -> ClassifierStatus:
        return self._status

    def model_info(self) -> ModelInfo:
        s = self._settings
        host = self._host or "unconfigured host"
        payload = (
            "decoded pixels re-encoded as lossless PNG (embedded metadata is not sent)"
            if s.http_payload == "pixels_png"
            else "the original file including its embedded metadata"
        )
        return ModelInfo(
            provider=f"Hosted inference endpoint ({host})",
            name=s.http_model_name or host,
            version=s.http_model_version or None,
            external=True,
            data_handling=(
                f"The uploaded image is sent to {host} for analysis: {payload}. "
                "That provider applies its own retention and logging policies, which ImageProof does not control."
            ),
            license=s.detector_license or None,
            description=s.detector_description or None,
        )

    # --- inference -------------------------------------------------------------------
    def _payload(self, inp: ClassifierInput) -> tuple[bytes, str]:
        if self._settings.http_payload == "original":
            return inp.image_bytes, inp.mime_type
        buffer = io.BytesIO()
        inp.rgb.save(buffer, "PNG", compress_level=1)
        return buffer.getvalue(), "image/png"

    def _headers(self, content_type: str) -> dict[str, str]:
        s = self._settings
        headers = {"Content-Type": content_type, "Accept": "application/json"}
        key = s.http_api_key.get_secret_value()
        if key:
            value = f"{s.http_auth_scheme} {key}".strip() if s.http_auth_scheme else key
            headers[s.http_auth_header] = value
        return headers

    async def classify(self, inp: ClassifierInput) -> list[LabelProbability]:
        if self._status.state != "ready" or self._client is None:
            code = "model_not_configured" if self._status.state == "not_configured" else "model_unavailable"
            raise ClassifierUnavailable(self._status.detail or "The inference endpoint is unavailable.", code=code)
        import asyncio

        body, content_type = await asyncio.to_thread(self._payload, inp)
        try:
            response = await self._client.post(
                self._settings.http_url, content=body, headers=self._headers(content_type)
            )
        except httpx.TimeoutException:
            raise ClassifierFailure("The inference provider timed out.", retryable=True) from None
        except httpx.HTTPError:
            raise ClassifierUnavailable("The inference provider could not be reached.", retryable=True) from None

        status = response.status_code
        if status in (401, 403):
            logger.error("provider_rejected_credentials status=%s", status)
            raise ClassifierUnavailable("The inference provider rejected the server's credentials.")
        if status == 429:
            retry = response.headers.get("retry-after", "")
            raise ClassifierFailure(
                "The inference provider's rate limit was reached.",
                retryable=True,
                retry_after=int(retry) if retry.isdigit() else None,
            )
        if status == 503:
            raise ClassifierUnavailable(
                "The inference provider is not ready (it may be starting up).", code="model_loading", retryable=True
            )
        if status >= 400:
            logger.error("provider_error status=%s", status)
            raise ClassifierFailure(f"The inference provider returned an error (HTTP {status}).", retryable=status >= 500)
        try:
            return self._parse(response.json())
        except (ValueError, KeyError, TypeError):
            raise ClassifierFailure("The inference provider returned an unexpected response format.") from None

    @staticmethod
    def _parse(payload: Any) -> list[LabelProbability]:
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            payload = payload[0]
        if not isinstance(payload, list) or not payload:
            raise ValueError("expected a non-empty list")
        scores = [LabelProbability(str(item["label"]), float(item["score"])) for item in payload]
        if any(not (0.0 <= s.score <= 1.0) for s in scores):
            raise ValueError("scores must be within [0, 1]")
        return scores


@register_provider("http_endpoint")
def _factory(settings: Settings) -> ImageClassifier:
    return HttpEndpointClassifier(settings)
