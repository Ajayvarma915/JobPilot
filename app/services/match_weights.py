"""Configurable, validated weights for the job match score.

The score is the sum of six components that together make 100 points. The defaults
below are the matcher's historical weights; edit data/match_weights.json to change
them. The file is validated on every load: unknown or missing components, negative
numbers, or a total other than 100 raise ValueError with a clear message instead of
silently producing odd scores.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

COMPONENTS = ("role", "seniority", "experience", "skills", "education", "location")

DEFAULT_WEIGHTS: dict[str, float] = {
    "role": 25.0,
    "seniority": 20.0,
    "experience": 20.0,
    "skills": 20.0,
    "education": 10.0,
    "location": 5.0,
}

WEIGHTS_PATH = Path(__file__).resolve().parents[2] / "data" / "match_weights.json"

_cache: dict[tuple[str, int, int], dict[str, float]] = {}


def validate_match_weights(weights: Any) -> dict[str, float]:
    if not isinstance(weights, dict):
        raise ValueError("Match weights must be an object mapping component names to numbers.")
    unknown = sorted(set(weights) - set(COMPONENTS))
    missing = sorted(set(COMPONENTS) - set(weights))
    if unknown:
        raise ValueError(f"Unknown match weight component(s): {', '.join(unknown)}. Allowed: {', '.join(COMPONENTS)}.")
    if missing:
        raise ValueError(f"Missing match weight component(s): {', '.join(missing)}.")
    cleaned: dict[str, float] = {}
    for name in COMPONENTS:
        value = weights[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Match weight '{name}' must be a number.")
        if value < 0:
            raise ValueError(f"Match weight '{name}' must not be negative.")
        cleaned[name] = float(value)
    total = sum(cleaned.values())
    if abs(total - 100.0) > 0.01:
        raise ValueError(f"Match weights must add up to 100, got {total:g}.")
    return cleaned


def load_match_weights(path: Path | None = None) -> dict[str, float]:
    """Return validated weights; defaults when the file does not exist."""
    target = Path(path) if path is not None else WEIGHTS_PATH
    if not target.is_file():
        return dict(DEFAULT_WEIGHTS)
    stat = target.stat()
    # Nanosecond mtime plus size: two quick rewrites must not look like the same file.
    key = (str(target), stat.st_mtime_ns, stat.st_size)
    if key in _cache:
        return dict(_cache[key])
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Match weights file {target.name} could not be read: {exc}") from exc
    weights = validate_match_weights(payload.get("weights") if isinstance(payload, dict) else payload)
    _cache.clear()
    _cache[key] = weights
    return dict(weights)
