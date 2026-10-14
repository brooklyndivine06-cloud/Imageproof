from __future__ import annotations

from typing import Callable

from app.config import Settings
from app.services.classifiers.base import ImageClassifier

ProviderFactory = Callable[[Settings], ImageClassifier]
_PROVIDERS: dict[str, ProviderFactory] = {}


def register_provider(name: str) -> Callable[[ProviderFactory], ProviderFactory]:
    def decorator(factory: ProviderFactory) -> ProviderFactory:
        _PROVIDERS[name] = factory
        return factory

    return decorator


def available_providers() -> list[str]:
    _load_builtin()
    return sorted(_PROVIDERS)


def _load_builtin() -> None:
    # Importing the modules registers the providers. Heavy ML imports happen lazily inside them.
    from app.services.classifiers import hf_local, http_endpoint  # noqa: F401


def build_classifier(settings: Settings) -> ImageClassifier:
    _load_builtin()
    try:
        factory = _PROVIDERS[settings.provider]
    except KeyError:
        raise ValueError(
            f"Unknown IMAGEPROOF_PROVIDER '{settings.provider}'. Available providers: {', '.join(sorted(_PROVIDERS))}"
        ) from None
    return factory(settings)
