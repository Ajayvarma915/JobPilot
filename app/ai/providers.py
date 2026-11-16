"""Model-provider abstraction for JobPilot's local AI features.

Default is the local Ollama server. No paid or external API is ever called unless
you register one explicitly (``register_provider``) AND select it with the
``JOBPILOT_AI_PROVIDER`` environment variable. Set that variable to ``none`` to turn
AI off completely; every AI feature has a deterministic fallback, so the product
stays usable either way.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Protocol

from app.ai import ollama_client


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderUnavailable(ProviderError):
    """The provider cannot be reached or is switched off (transient; retrying may help)."""


class ProviderModelMissing(ProviderError):
    """The configured model is not installed (retrying will not help)."""


class ProviderResponseError(ProviderError):
    """The provider answered with something unusable."""


class LLMProvider(Protocol):
    name: str

    def model_name(self) -> str: ...

    def status(self) -> dict[str, Any]: ...

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], *, system: str | None = None, timeout: int | None = None
    ) -> str: ...


class OllamaProvider:
    """Local models served by Ollama (default model from JOBPILOT_OLLAMA_MODEL, gemma3:4b)."""

    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def model_name(self) -> str:
        return self._model or ollama_client.OLLAMA_MODEL

    def status(self) -> dict[str, Any]:
        status = dict(ollama_client.get_status())
        status["provider"] = self.name
        return status

    def generate_structured(
        self, prompt: str, schema: dict[str, Any], *, system: str | None = None, timeout: int | None = None
    ) -> str:
        kwargs: dict[str, Any] = {"model": self._model, "system": system}
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            return ollama_client.generate_structured(prompt, schema, **kwargs)
        except ollama_client.OllamaUnavailableError as exc:
            raise ProviderUnavailable(str(exc)) from exc
        except ollama_client.OllamaModelNotFoundError as exc:
            raise ProviderModelMissing(str(exc)) from exc
        except ollama_client.OllamaError as exc:
            raise ProviderResponseError(str(exc)) from exc


class DisabledProvider:
    """Selected with JOBPILOT_AI_PROVIDER=none: AI is off, fallbacks are used."""

    name = "none"

    def model_name(self) -> str:
        return "none"

    def status(self) -> dict[str, Any]:
        return {"provider": self.name, "available": False, "configured_model": None, "model_installed": False,
                "installed_models": [], "message": "AI is disabled (JOBPILOT_AI_PROVIDER=none)."}

    def generate_structured(self, prompt: str, schema: dict[str, Any], *, system: str | None = None, timeout: int | None = None) -> str:
        raise ProviderUnavailable("AI is disabled (JOBPILOT_AI_PROVIDER=none).")


_REGISTRY: dict[str, Callable[[], LLMProvider]] = {
    "ollama": OllamaProvider,
    "none": DisabledProvider,
    "disabled": DisabledProvider,
}


def register_provider(name: str, factory: Callable[[], LLMProvider]) -> None:
    """Make a provider selectable by name. Nothing is registered besides Ollama by default."""
    _REGISTRY[name.strip().lower()] = factory


def get_provider(name: str | None = None) -> LLMProvider:
    selected = (name or os.getenv("JOBPILOT_AI_PROVIDER") or "ollama").strip().lower()
    factory = _REGISTRY.get(selected)
    if factory is None:
        raise ValueError(
            f"Unknown AI provider {selected!r}. Available: {', '.join(sorted(_REGISTRY))}. "
            "External providers must be registered explicitly; none are enabled by default."
        )
    return factory()
