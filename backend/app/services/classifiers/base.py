"""Classifier provider interface.

To add a provider: subclass :class:`ImageClassifier`, implement ``status``,
``model_info`` and ``classify``, and register it with ``@register_provider("name")``
(see ``registry.py``). Select it with ``IMAGEPROOF_PROVIDER=name``. Nothing else
in the application needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from PIL import Image

from app.schemas import ModelInfo


@dataclass(frozen=True)
class LabelProbability:
    label: str
    score: float


@dataclass
class ClassifierInput:
    image_bytes: bytes  # the validated upload, exactly as received
    mime_type: str
    rgb: Image.Image  # decoded, orientation-corrected 8-bit RGB


@dataclass(frozen=True)
class ClassifierStatus:
    state: Literal["ready", "loading", "not_configured", "error"]
    detail: str | None = None


class ClassifierUnavailable(Exception):
    """The classifier cannot serve requests right now (not configured, still loading, rejected credentials)."""

    def __init__(self, message: str, *, code: str = "model_unavailable", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ClassifierFailure(Exception):
    """The classifier was reachable but the inference failed for this request."""

    def __init__(self, message: str, *, retryable: bool = False, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class ImageClassifier(ABC):
    provider_id: str = "base"

    async def startup(self) -> None:  # pragma: no cover - default no-op
        return None

    async def shutdown(self) -> None:  # pragma: no cover - default no-op
        return None

    @abstractmethod
    def status(self) -> ClassifierStatus: ...

    @abstractmethod
    def model_info(self) -> ModelInfo: ...

    @abstractmethod
    async def classify(self, inp: ClassifierInput) -> list[LabelProbability]:
        """Return a probability-like score for every label the model emits."""
