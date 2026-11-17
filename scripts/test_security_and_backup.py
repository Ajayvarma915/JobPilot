"""Tests for the optional API token and the backup/restore tool (temp files only)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_security.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, engine  # noqa: E402
from scripts import backup_database as backup  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_api_token() -> None:
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    os.environ.pop("JOBPILOT_API_TOKEN", None)
    check(client.get("/api/dashboard/stats").status_code == 200, "no token configured = local mode, unchanged")
    os.environ["JOBPILOT_API_TOKEN"] = "s3cret-token-value"
    try:
        check(client.get("/api/dashboard/stats").status_code == 401, "a configured token is required")
        refused = client.get("/api/dashboard/stats")
        check(refused.headers.get("www-authenticate") == "Bearer" and "token" in refused.json()["detail"].lower(), "clear 401")
        check(client.get("/api/dashboard/stats", headers={"Authorization": "Bearer wrong"}).status_code == 401, "wrong token")
        check(client.get("/api/dashboard/stats", headers={"Authorization": "Bearer s3cret-token-value"}).status_code == 200, "Bearer token works")
        check(client.get("/api/dashboard/stats", headers={"X-JobPilot-Token": "s3cret-token-value"}).status_code == 200, "header token works")
        check(client.get("/api/dashboard/stats", headers={"Authorization": "s3cret-token-value"}).status_code == 401, "scheme is required")
        check(client.post("/api/answers/draft", json={"question": "x"}).status_code == 401, "writes are protected too")
        check(client.get("/api/health").status_code == 200, "the health check stays open")
        check(client.get("/api/email/oauth/callback").status_code != 401, "the Google redirect cannot carry a header, so it stays reachable")
        check(client.get("/").status_code == 200, "the root page stays open")
        preflight = client.options("/api/dashboard/stats", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET",
                                                                    "Access-Control-Request-Headers": "authorization"})
        check(preflight.status_code == 200 and "authorization" in preflight.headers.get("access-control-allow-headers", "").lower(), "CORS preflight allows the token header")
        rejected = client.get("/api/dashboard/stats", headers={"Origin": "http://127.0.0.1:5173"})
        check(rejected.status_code == 401 and rejected.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173",
              "a rejected browser request still carries CORS headers, so the page sees a 401, not a CORS error")
    finally:
        os.environ.pop("JOBPILOT_API_TOKEN", None)
    source = (Path(api_main.__file__)).read_text(encoding="utf-8")
    check("hmac.compare_digest" in source, "the token is compared in constant time")


def test_cors_origins_are_configurable() -> None:
    os.environ["JOBPILOT_CORS_ORIGINS"] = "https://jobs.example.com/, https://other.example.com"
    try:
        check(api_main._cors_origins() == ["https://jobs.example.com", "https://other.example.com"], api_main._cors_origins())
    finally:
        os.environ.pop("JOBPILOT_CORS_ORIGINS", None)
    check(api_main._cors_origins() == ["http://localhost:5173", "http://127.0.0.1:5173"], "safe local default")


def _make_db(path: Path, rows: int) -> None:
    connection = sqlite3.connect(str(path))
    connection.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, v TEXT)")
    connection.execute("DELETE FROM t")
    connection.executemany("INSERT INTO t (v) VALUES (?)", [(f"row {i}",) for i in range(rows)])
    connection.commit()
    connection.close()


def _count(path: Path) -> int:
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        connection.close()


def test_backup_restore_and_retention() -> None:
    root = Path(_TEMP_DIR.name) / "backup_test"
    root.mkdir()
    live = root / "live.db"
    backups = root / "backups"
    _make_db(live, 5)

    first = backup.create_backup(live, backups, keep=2)
    check(first.is_file() and _count(first) == 5 and backup.integrity_ok(first), "backup is a verified, complete copy")
    _make_db(live, 8)
    time.sleep(0.01)
    second = backup.create_backup(live, backups, keep=2)
    time.sleep(0.01)
    third = backup.create_backup(live, backups, keep=2)
    check(sorted(p.name for p in backups.glob("jobpilot_*.db")) == sorted([second.name, third.name]), "only the newest 2 regular backups are kept")
    check(_count(second) == 8, "later backups hold later data")

    _make_db(live, 1)
    safety = backup.restore_backup(second, live, backups)
    check(_count(live) == 8, "restore replaces the live data")
    check(safety.is_file() and _count(safety) == 1 and safety.name.startswith("pre_restore_"), "the previous data is saved before a restore")
    backup.create_backup(live, backups, keep=1)
    check(safety.is_file(), "safety copies are not pruned by retention")

    broken = root / "broken.db"
    broken.write_bytes(b"this is not a database" * 100)
    for action, label in ((lambda: backup.restore_backup(broken, live, backups), "corrupt backup"),
                          (lambda: backup.restore_backup(root / "missing.db", live, backups), "missing backup"),
                          (lambda: backup.create_backup(root / "nope.db", backups), "missing source")):
        try:
            action()
        except backup.BackupError:
            continue
        raise AssertionError(f"{label} was accepted")
    check(_count(live) == 8, "a refused restore leaves the live database untouched")


def test_cli_requires_confirmation() -> None:
    root = Path(_TEMP_DIR.name) / "cli_test"
    root.mkdir()
    live = root / "live.db"
    _make_db(live, 3)
    other = root / "other.db"
    _make_db(other, 9)
    original_argv, original_resolve = sys.argv, backup.resolve_database_path
    backup.resolve_database_path = lambda: live
    try:
        sys.argv = ["backup_database.py", "--restore", str(other)]
        check(backup.main() == 2 and _count(live) == 3, "restore without --yes changes nothing")
        sys.argv = ["backup_database.py", "--restore", str(other), "--yes"]
        check(backup.main() == 0 and _count(live) == 9, "restore with --yes works")
    finally:
        sys.argv, backup.resolve_database_path = original_argv, original_resolve


TESTS = [
    ("Optional API token", test_api_token),
    ("CORS origins are configurable with a safe default", test_cors_origins_are_configurable),
    ("Backup, verification, retention and restore", test_backup_restore_and_retention),
    ("Restore needs explicit confirmation", test_cli_requires_confirmation),
]


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
