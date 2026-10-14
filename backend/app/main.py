"""FastAPI application factory.

Run with:  uvicorn app.main:create_app --factory
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.formparsers import MultiPartParser

from app.api.v1.routes import router
from app.config import APP_VERSION, Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.rate_limit import SlidingWindowRateLimiter
from app.services.assessment import load_calibration
from app.services.classifiers import ImageClassifier, build_classifier
from app.services.evaluation_report import load_evaluation_summary
from app.services.pipeline import AnalysisService

logger = logging.getLogger("imageproof")

# Multipart framing overhead allowed on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def create_app(settings: Settings | None = None, classifier: ImageClassifier | None = None) -> FastAPI:
    """Build the application.

    ``classifier`` exists so tests can inject a test double. Production code
    paths always build the classifier from configuration.
    """
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if "*" in settings.cors_origin_list:
        raise ValueError("IMAGEPROOF_CORS_ORIGINS must list explicit origins; '*' is not allowed.")

    # Keep uploads in memory: Starlette spools multipart files to a temp file above 1 MB by default.
    # Raising the threshold to the upload limit means no temporary files are written for valid uploads.
    MultiPartParser.spool_max_size = settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        active = classifier or build_classifier(settings)
        await active.startup()
        calibration = load_calibration(settings, active.model_info())
        app.state.settings = settings
        app.state.classifier = active
        app.state.calibration = calibration
        app.state.analysis = AnalysisService(settings, active, calibration)
        app.state.rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)
        app.state.evaluation = load_evaluation_summary(settings, active.model_info())
        logger.info("startup_complete provider=%s environment=%s", settings.provider, settings.environment)
        try:
            yield
        finally:
            await active.shutdown()

    production = settings.environment == "production"
    app = FastAPI(
        title="ImageProof API",
        version=APP_VERSION,
        description="Image authenticity analysis: classifier, metadata, C2PA provenance and forensic measurements.",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    install_error_handlers(app)
    app.include_router(router)

    # Middleware order: last added runs first (outermost).
    app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES)
    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
    app.add_middleware(RequestContextMiddleware)
    return app
