"""An unexpected server error reaches the browser as readable JSON with CORS headers (temp database)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "errors.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import engine  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_unexpected_error_is_readable_and_has_cors() -> None:
    @api_main.app.get("/api/_boom_for_test")
    def boom() -> None:
        raise RuntimeError("database exploded")

    client = TestClient(api_main.app, raise_server_exceptions=False)
    response = client.get("/api/_boom_for_test", headers={"Origin": "http://127.0.0.1:5173"})
    check(response.status_code == 500, response.status_code)
    check("RuntimeError" in response.json()["detail"] and "database exploded" in response.json()["detail"], response.text)
    check(response.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173", "CORS headers are present, so the browser can show the message")
    check(client.get("/api/sync/status").status_code == 200, "normal requests are unaffected")
    check(client.get("/api/openapi-not-here").status_code == 404, "expected errors keep their own status")


TESTS = [("Unexpected errors become readable JSON with CORS headers", test_unexpected_error_is_readable_and_has_cors)]


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
