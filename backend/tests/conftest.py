"""Shared test helpers.

IMPORTANT: ``StubClassifier`` is a *test double* used only by the test-suite to
exercise the API around the classifier. It is never importable by the running
application and is not a detector.
"""

from __future__ import annotations

import io
import asyncio

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.schemas import ModelInfo
from app.services.classifiers.base import (
    ClassifierInput,
    ClassifierStatus,
    ImageClassifier,
    LabelProbability,
)


class StubClassifier(ImageClassifier):
    provider_id = "test_double"

    def __init__(self, ai_score: float = 0.5, state: str = "ready", error: Exception | None = None, delay: float = 0.0):
        self.ai_score = ai_score
        self._state = state
        self.error = error
        self.delay = delay
        self.calls = 0

    def status(self) -> ClassifierStatus:
        return ClassifierStatus(self._state, None if self._state == "ready" else "stub state")  # type: ignore[arg-type]

    def model_info(self) -> ModelInfo:
        return ModelInfo(
            provider="Test double",
            name="test/stub-model",
            version="0",
            external=False,
            data_handling="In-process test double.",
        )

    async def classify(self, inp: ClassifierInput) -> list[LabelProbability]:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return [LabelProbability("artificial", self.ai_score), LabelProbability("human", 1 - self.ai_score)]


def make_settings(**overrides) -> Settings:
    values = dict(
        environment="test",
        ai_labels="artificial",
        real_labels="human",
        max_upload_mb=1,
        rate_limit_requests=100,
        log_level="WARNING",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def noise_image(width=320, height=240, seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    gradient = np.linspace(40, 200, width)[None, :, None] * np.ones((height, 1, 3))
    arr = np.clip(gradient + rng.normal(0, 12, (height, width, 3)), 0, 255).astype("uint8")
    return Image.fromarray(arr)


def to_bytes(img: Image.Image, fmt="JPEG", **kwargs) -> bytes:
    buf = io.BytesIO()
    img.save(buf, fmt, **kwargs)
    return buf.getvalue()


def jpeg_with_exif(make="TestCam", model="Model 1", software=None) -> bytes:
    img = noise_image()
    exif = Image.Exif()
    exif[271] = make
    exif[272] = model
    if software:
        exif[305] = software
    ifd = exif.get_ifd(0x8769)
    from PIL.TiffImagePlugin import IFDRational

    ifd[33434] = IFDRational(1, 250)
    ifd[33437] = IFDRational(18, 10)
    ifd[34855] = 200
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    return to_bytes(img, "JPEG", quality=90, exif=exif)


@pytest.fixture
def stub():
    return StubClassifier(ai_score=0.5)


@pytest.fixture
def client_factory():
    clients: list[TestClient] = []

    def make(classifier: ImageClassifier | None = None, **setting_overrides) -> TestClient:
        app = create_app(make_settings(**setting_overrides), classifier=classifier or StubClassifier())
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for c in clients:
        c.__exit__(None, None, None)


def post_image(client: TestClient, data: bytes, filename="photo.jpg", content_type="image/jpeg"):
    return client.post("/api/v1/analyze", files={"file": (filename, data, content_type)})
