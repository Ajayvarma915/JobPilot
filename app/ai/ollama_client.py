"""Small, testable client for the local Ollama HTTP API."""
from __future__ import annotations

import requests

from app.config import OLLAMA_API_BASE, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL


class OllamaError(RuntimeError):
    """Base exception for local Ollama failures."""


class OllamaUnavailableError(OllamaError):
    """Ollama is not running or cannot be reached."""


class OllamaModelNotFoundError(OllamaError):
    """The configured model is not installed locally."""


class OllamaResponseError(OllamaError):
    """Ollama returned a response that JobPilot cannot use."""


def list_models() -> list[str]:
    """Return installed model names from Ollama's /api/tags endpoint."""
    try:
        response = requests.get(
            f"{OLLAMA_API_BASE}/api/tags",
            timeout=(3, 8),
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise OllamaUnavailableError(
            "Could not reach Ollama at " + OLLAMA_API_BASE
        ) from exc
    except (ValueError, TypeError) as exc:
        raise OllamaResponseError("Ollama returned invalid model-list JSON.") from exc

    if not isinstance(payload, dict):
        raise OllamaResponseError("Ollama model-list response must be a JSON object.")
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise OllamaResponseError("Ollama model-list response has an invalid shape.")
    return [
        str(item.get("name", "")).strip()
        for item in models
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]


def get_status() -> dict[str, object]:
    """Return a non-throwing diagnostic snapshot for the local AI service."""
    try:
        models = list_models()
    except OllamaError as exc:
        return {
            "provider": "ollama",
            "available": False,
            "configured_model": OLLAMA_MODEL,
            "model_installed": False,
            "installed_models": [],
            "message": str(exc),
        }

    # Require an exact tag match; gemma3:1b must not satisfy gemma3:4b.
    model_installed = OLLAMA_MODEL in models
    return {
        "provider": "ollama",
        "available": True,
        "configured_model": OLLAMA_MODEL,
        "model_installed": model_installed,
        "installed_models": models,
        "message": (
            "Configured model is installed."
            if model_installed
            else f"Ollama is running, but {OLLAMA_MODEL!r} is not installed."
        ),
    }


def generate(
    prompt: str,
    model: str | None = None,
    *,
    system: str | None = None,
    timeout: int = OLLAMA_TIMEOUT_SECONDS,
) -> str:
    """Generate plain text. Kept backward-compatible with the original client."""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt must not be empty.")

    selected_model = model or OLLAMA_MODEL
    payload: dict[str, object] = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    if system:
        payload["system"] = system

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.ConnectionError as exc:
        raise OllamaUnavailableError(
            "Ollama is not reachable. Start the Ollama application and retry."
        ) from exc
    except requests.Timeout as exc:
        raise OllamaUnavailableError(
            f"Ollama did not respond within {timeout} seconds."
        ) from exc
    except requests.RequestException as exc:
        message = getattr(getattr(exc, "response", None), "text", "")
        if "model" in str(message).lower() and "not found" in str(message).lower():
            raise OllamaModelNotFoundError(
                f"Ollama model {selected_model!r} is not installed."
            ) from exc
        raise OllamaError("Ollama generation request failed.") from exc
    except (ValueError, TypeError) as exc:
        raise OllamaResponseError("Ollama returned invalid response JSON.") from exc

    result = data.get("response") if isinstance(data, dict) else None
    if not isinstance(result, str) or not result.strip():
        raise OllamaResponseError("Ollama returned an empty or invalid response.")
    return result.strip()


def generate_structured(
    prompt: str,
    schema: dict[str, object],
    model: str | None = None,
    *,
    system: str | None = None,
    timeout: int = OLLAMA_TIMEOUT_SECONDS,
) -> str:
    """Generate JSON constrained by an Ollama-supported JSON schema."""
    if not prompt or not prompt.strip():
        raise ValueError("Prompt must not be empty.")

    selected_model = model or OLLAMA_MODEL
    payload: dict[str, object] = {
        "model": selected_model,
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "options": {"temperature": 0.1},
    }
    if system:
        payload["system"] = system

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except requests.ConnectionError as exc:
        raise OllamaUnavailableError(
            "Ollama is not reachable. Start the Ollama application and retry."
        ) from exc
    except requests.Timeout as exc:
        raise OllamaUnavailableError(
            f"Ollama did not respond within {timeout} seconds."
        ) from exc
    except requests.RequestException as exc:
        message = getattr(getattr(exc, "response", None), "text", "")
        if "model" in str(message).lower() and "not found" in str(message).lower():
            raise OllamaModelNotFoundError(
                f"Ollama model {selected_model!r} is not installed."
            ) from exc
        raise OllamaError("Ollama structured generation request failed.") from exc
    except (ValueError, TypeError) as exc:
        raise OllamaResponseError("Ollama returned invalid response JSON.") from exc

    result = data.get("response") if isinstance(data, dict) else None
    if not isinstance(result, str) or not result.strip():
        raise OllamaResponseError("Ollama returned an empty or invalid response.")
    return result.strip()
