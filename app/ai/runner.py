"""Run one structured local-AI task with retries, validation, caching and safe logging."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.ai.providers import (
    LLMProvider,
    ProviderModelMissing,
    ProviderResponseError,
    ProviderUnavailable,
    get_provider,
)
from app.db.models import AiCacheEntry

logger = logging.getLogger("jobpilot.ai")

OK = "ok"
UNAVAILABLE = "unavailable"
MODEL_MISSING = "model_missing"
INVALID = "invalid_output"


@dataclass
class AiRun:
    status: str
    result: dict[str, Any] | None
    cached: bool
    provider: str
    model: str
    prompt_version: str
    attempts: int
    error: str | None = None


def make_cache_key(task: str, prompt_version: str, provider: str, model: str, parts: dict[str, Any]) -> str:
    payload = json.dumps(
        {"task": task, "prompt_version": prompt_version, "provider": provider, "model": model, "parts": parts},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_table(session: Session) -> None:
    AiCacheEntry.__table__.create(bind=session.get_bind(), checkfirst=True)


def run_structured(
    *,
    task: str,
    prompt_version: str,
    prompt: str,
    schema: dict[str, Any],
    system: str | None,
    validate: Callable[[str], dict[str, Any]],
    cache_parts: dict[str, Any],
    session: Session | None = None,
    provider: LLMProvider | None = None,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    use_cache: bool = True,
    timeout: int | None = None,
) -> AiRun:
    """Ask the provider, validate the answer, cache it. Never raises for provider problems.

    - Unreachable provider: retried with exponential backoff, then status "unavailable".
    - Missing model: not retried, status "model_missing".
    - Unusable output (invalid JSON / failed validation): retried once more, then "invalid_output".
    The caller decides what deterministic fallback to show for any non-ok status.
    Logging records metadata only (task, version, model, sizes, duration), never prompt text.
    """
    chosen = provider or get_provider()
    model = chosen.model_name()
    key = make_cache_key(task, prompt_version, chosen.name, model, cache_parts)
    started = time.monotonic()

    def done(run: AiRun) -> AiRun:
        logger.info(
            "ai_task task=%s prompt_version=%s provider=%s model=%s status=%s attempts=%d cached=%s input_chars=%d duration_ms=%d",
            task, prompt_version, run.provider, run.model, run.status, run.attempts, run.cached, len(prompt),
            int((time.monotonic() - started) * 1000),
        )
        return run

    if use_cache and session is not None:
        _ensure_table(session)
        entry = session.get(AiCacheEntry, key)
        if entry is not None:
            try:
                return done(AiRun(OK, json.loads(entry.result_json), True, chosen.name, model, prompt_version, 0))
            except json.JSONDecodeError:
                session.delete(entry)  # a damaged cache row is just ignored and replaced

    attempts = 0
    unusable_retries = 0
    last_error = "unknown error"
    while attempts < max_attempts:
        attempts += 1
        try:
            raw = chosen.generate_structured(prompt, schema, system=system, timeout=timeout)
        except ProviderModelMissing as exc:
            return done(AiRun(MODEL_MISSING, None, False, chosen.name, model, prompt_version, attempts, str(exc)))
        except ProviderUnavailable as exc:
            last_error = str(exc)
            if attempts >= max_attempts:
                return done(AiRun(UNAVAILABLE, None, False, chosen.name, model, prompt_version, attempts, last_error))
            sleep(backoff_seconds * (2 ** (attempts - 1)))
            continue
        except ProviderResponseError as exc:
            last_error = str(exc)
        else:
            try:
                result = validate(raw)
            except (ValueError, TypeError, ProviderResponseError) as exc:
                last_error = f"Model output failed validation: {exc}"
            else:
                if use_cache and session is not None:
                    session.merge(AiCacheEntry(
                        cache_key=key, task=task, prompt_version=prompt_version, provider=chosen.name, model=model,
                        result_json=json.dumps(result, ensure_ascii=False), created_at=datetime.utcnow(),
                    ))
                    session.commit()
                return done(AiRun(OK, result, False, chosen.name, model, prompt_version, attempts))
        unusable_retries += 1
        if unusable_retries >= 2:
            break
    return done(AiRun(INVALID, None, False, chosen.name, model, prompt_version, attempts, last_error))
