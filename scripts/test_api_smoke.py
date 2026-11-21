"""Smoke test: every GET endpoint answers sensibly against an EMPTY database built from the real tables.

Catches broken queries, missing tables and missing columns across the whole API at once (the kind of bug
that only showed up on a real database). A 503 is accepted only for endpoints that need something outside
the app (Gmail sign-in, a local AI model, files that do not exist yet); anything else must not be a 5xx.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "smoke.db")

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, engine  # noqa: E402

# Endpoints that legitimately cannot answer without an outside service or an uploaded file.
NEEDS_OUTSIDE_THINGS = ("/api/ai/", "/api/email/oauth", "/api/email/connect", "/api/ollama", "/download", "/api/health/ai")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_every_get_endpoint_survives_an_empty_real_schema() -> None:
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app, raise_server_exceptions=False)
    problems: list[str] = []
    checked = 0
    for route in api_main.app.routes:
        if not isinstance(route, APIRoute) or "GET" not in route.methods or not route.path.startswith("/api/"):
            continue
        if any(marker in route.path for marker in NEEDS_OUTSIDE_THINGS):
            continue
        path = re.sub(r"\{[^}]+\}", "1", route.path)
        response = client.get(path)
        checked += 1
        if response.status_code >= 500 and response.status_code != 503:
            problems.append(f"GET {path} -> {response.status_code}: {response.text[:140]}")
    check(checked >= 20, f"expected to exercise at least 20 GET endpoints, got {checked}")
    check(not problems, "\n  " + "\n  ".join(problems))


TESTS = [("Every GET endpoint survives an empty database built from the real tables", test_every_get_endpoint_survives_an_empty_real_schema)]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    engine.dispose()
    api_main.engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
