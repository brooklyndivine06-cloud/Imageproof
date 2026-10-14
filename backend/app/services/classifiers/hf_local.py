"""Self-hosted image classifier using Hugging Face Transformers.

Runs entirely on this server: uploaded pixels are never sent to a third party.
Requires the optional ML dependencies (``pip install -r requirements-ml.txt``).

Security: remote code is never executed (``trust_remote_code=False``) and only
``.safetensors`` weights are loaded, so a malicious pickle cannot run code.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

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


class HuggingFaceLocalClassifier(ImageClassifier):
    provider_id = "huggingface_local"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state: ClassifierStatus
        if not settings.hf_model_id:
            self._state = ClassifierStatus("not_configured", "IMAGEPROOF_HF_MODEL_ID is not set.")
        else:
            self._state = ClassifierStatus("loading", "The model has not been loaded yet.")
        self._processor: Any = None
        self._model: Any = None
        self._torch: Any = None
        self._device: str = "cpu"
        self._revision: str | None = settings.hf_model_revision or None
        self._load_task: asyncio.Task[None] | None = None

    # --- lifecycle ---------------------------------------------------------------
    async def startup(self) -> None:
        if self._state.state == "not_configured":
            return
        self._load_task = asyncio.create_task(asyncio.to_thread(self._load))

    async def shutdown(self) -> None:
        if self._load_task and not self._load_task.done():
            self._load_task.cancel()

    def _load(self) -> None:
        s = self._settings
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForImageClassification
        except ImportError:
            self._state = ClassifierStatus(
                "error",
                "ML dependencies are not installed. Run: pip install -r requirements-ml.txt",
            )
            logger.error("classifier_load_failed reason=missing_ml_dependencies")
            return
        try:
            kwargs: dict[str, Any] = {
                "revision": s.hf_model_revision or None,
                "local_files_only": s.hf_local_files_only,
                "trust_remote_code": False,
            }
            processor = AutoImageProcessor.from_pretrained(s.hf_model_id, backend=s.hf_processor_backend, **kwargs)
            model = AutoModelForImageClassification.from_pretrained(s.hf_model_id, use_safetensors=True, **kwargs)
            device = s.hf_device
            if device == "auto":
                if torch.cuda.is_available():
                    device = "cuda"
                elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"
            model.to(device)
            model.eval()
            self._torch, self._processor, self._model, self._device = torch, processor, model, device
            commit = getattr(model.config, "_commit_hash", None)
            if commit and not self._revision:
                self._revision = str(commit)
            self._state = ClassifierStatus("ready", None)
            logger.info("classifier_ready provider=%s model=%s device=%s", self.provider_id, s.hf_model_id, device)
        except Exception as exc:
            # Do not include exception text: it can contain local paths or tokens.
            self._state = ClassifierStatus(
                "error", f"The model could not be loaded ({type(exc).__name__}). Check IMAGEPROOF_HF_MODEL_ID, network access and server logs."
            )
            logger.error("classifier_load_failed reason=%s", type(exc).__name__)

    # --- interface ------------------------------------------------------------------
    def status(self) -> ClassifierStatus:
        return self._state

    def model_info(self) -> ModelInfo:
        s = self._settings
        return ModelInfo(
            provider="Hugging Face Transformers (self-hosted)",
            name=s.hf_model_id or "not configured",
            version=self._revision,
            external=False,
            data_handling="Images are analysed on this server and are not sent to any third party.",
            license=s.detector_license or None,
            description=s.detector_description or None,
        )

    async def classify(self, inp: ClassifierInput) -> list[LabelProbability]:
        state = self._state
        if state.state == "loading":
            raise ClassifierUnavailable("The detection model is still loading.", code="model_loading", retryable=True)
        if state.state != "ready":
            code = "model_not_configured" if state.state == "not_configured" else "model_unavailable"
            raise ClassifierUnavailable(state.detail or "The detection model is unavailable.", code=code)
        try:
            return await asyncio.to_thread(self._infer, inp)
        except ClassifierFailure:
            raise
        except Exception as exc:
            logger.error("inference_failed type=%s", type(exc).__name__)
            raise ClassifierFailure("The model failed while analysing this image.") from None

    def _infer(self, inp: ClassifierInput) -> list[LabelProbability]:
        torch = self._torch
        with torch.inference_mode():
            batch = self._processor(images=inp.rgb, return_tensors="pt")
            batch = {k: v.to(self._device) for k, v in batch.items()}
            logits = self._model(**batch).logits
            probs = torch.softmax(logits.float(), dim=-1)[0].cpu().tolist()
        id2label = self._model.config.id2label
        return [LabelProbability(str(id2label[i]), float(p)) for i, p in enumerate(probs)]


@register_provider("huggingface_local")
def _factory(settings: Settings) -> ImageClassifier:
    return HuggingFaceLocalClassifier(settings)
