"""Application configuration.

All settings come from environment variables prefixed with ``IMAGEPROOF_`` (or a
local ``.env`` file). Secrets such as provider API keys are only ever read here,
on the server, and are never included in any API response.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "1.0.0"

# Detected from file contents, never from the file name or declared MIME type.
SUPPORTED_FORMATS: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IMAGEPROOF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General -----------------------------------------------------------
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    # Comma-separated list of browser origins allowed to call the API directly.
    # Leave empty when the frontend proxies requests (the default setup).
    cors_origins: str = ""
    # Number of reverse proxies in front of this API that append to
    # X-Forwarded-For. 0 means "use the socket peer address".
    trusted_proxy_count: int = 0

    # --- Upload limits -----------------------------------------------------
    max_upload_mb: float = 10.0
    min_image_side: int = 64
    max_image_pixels: int = 40_000_000
    analysis_timeout_seconds: float = 60.0
    max_concurrent_analyses: int = 2
    queue_wait_seconds: float = 5.0

    # --- Rate limiting (per client IP, in-process) -------------------------
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 600

    # --- Classifier selection ----------------------------------------------
    provider: str = "huggingface_local"
    # Free-text values shown to users; set them to match your model's card.
    detector_license: str = ""
    detector_description: str = ""

    # Label mapping (comma separated, case-insensitive). Required: the app will
    # not guess which label of a model means "AI-generated".
    ai_labels: str = ""
    real_labels: str = ""

    # Decision thresholds on the AI-label score. Used unless a matching
    # calibration file (produced by the evaluation harness) is loaded.
    ai_threshold: float = 0.85
    real_threshold: float = 0.15
    degrade_low_reliability: bool = True
    calibration_file: str = ""
    evaluation_report: str = ""

    # --- Provider: huggingface_local ---------------------------------------
    hf_model_id: str = ""
    hf_model_revision: str = ""
    hf_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    hf_processor_backend: Literal["pil", "torchvision"] = "pil"
    hf_local_files_only: bool = False

    # --- Provider: http_endpoint -------------------------------------------
    http_url: str = ""
    http_api_key: SecretStr = SecretStr("")
    http_auth_header: str = "Authorization"
    http_auth_scheme: str = "Bearer"
    http_payload: Literal["pixels_png", "original"] = "pixels_png"
    http_timeout_seconds: float = 30.0
    http_model_name: str = ""
    http_model_version: str = ""

    # --- Evidence modules --------------------------------------------------
    enable_provenance: bool = True
    enable_forensics: bool = True

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        if not (0.0 < self.real_threshold < self.ai_threshold < 1.0):
            raise ValueError(
                "IMAGEPROOF_REAL_THRESHOLD must be lower than IMAGEPROOF_AI_THRESHOLD "
                "and both must be strictly between 0 and 1"
            )
        if self.max_upload_mb <= 0 or self.max_upload_mb > 100:
            raise ValueError("IMAGEPROOF_MAX_UPLOAD_MB must be between 0 and 100")
        if self.max_concurrent_analyses < 1:
            raise ValueError("IMAGEPROOF_MAX_CONCURRENT_ANALYSES must be >= 1")
        return self

    # Convenience accessors -------------------------------------------------
    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def cors_origin_list(self) -> list[str]:
        return split_csv(self.cors_origins)

    @property
    def ai_label_set(self) -> set[str]:
        return {label.lower() for label in split_csv(self.ai_labels)}

    @property
    def real_label_set(self) -> set[str]:
        return {label.lower() for label in split_csv(self.real_labels)}


@lru_cache
def get_settings() -> Settings:
    return Settings()
