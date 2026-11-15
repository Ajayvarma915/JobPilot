"""Tests for the change summary, its API endpoint and the scheduled-sync runner (temp DB only)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_sync_summary.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, select  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.db.models import JobVersion  # noqa: E402
from app.services.sync_summary import build_change_summary  # noqa: E402
from scripts import run_scheduled_sync  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _data(i: int, description: str = "Minimum qualifications: 1 year.") -> dict:
    return {"source": "lever:acme", "external_id": str(i), "title": f"Engineer {i}", "location": ["Pune, India"],
            "url": f"https://acme.example/{i}", "description": description, "employment_type": "Full-time"}


def _reset() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_summary_counts_and_no_duplicate_events() -> None:
    _reset()
    session = SessionLocal()
    try:
        empty = build_change_summary(session)
        check(empty["tracking_available"] is False and empty["note"], "no history yet is reported honestly, not as zeros")

        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        for i in (1, 2, 3):
            repo.upsert_job_detailed(company, _data(i))
        repo.upsert_job_detailed(company, _data(1, "Minimum qualifications: 3 years."))  # updated
        repo.mark_missing_inactive(company, ["lever:acme"], {"1", "2"})                      # 3 removed
        repo.upsert_job_detailed(company, _data(3))                                          # reactivated
        # Re-running the identical sync must not create new events.
        for i in (1, 2):
            repo.upsert_job_detailed(company, _data(i, "Minimum qualifications: 3 years." if i == 1 else "Minimum qualifications: 1 year."))
        session.commit()

        summary = build_change_summary(session, days=7)
        check(summary["tracking_available"] is True, "tracking available once versions exist")
        check(summary["counts"] == {"created": 3, "updated": 1, "reactivated": 1, "removed": 1}, f"counts: {summary['counts']}")
        check(summary["by_company"][0]["company"] == "Acme" and summary["by_company"][0]["total"] == 6, f"{summary['by_company']}")
        events = [(e["event"], e["title"]) for e in summary["recent"]]
        check(len(events) == len(set(events)) or len(events) == 6, "each event appears once")
        check(any(e["event"] == "updated" and e["changed_fields"] == ["description"] for e in summary["recent"]), "changed fields listed")
        check(summary["jobs_active"] == 3 and summary["jobs_inactive"] == 0, "active/inactive totals")

        # Window: events older than the window are excluded; baseline rows never count as events.
        old = session.scalars(select(JobVersion)).all()
        for version in old:
            version.captured_at = datetime.utcnow() - timedelta(days=30)
        session.commit()
        check(build_change_summary(session, days=7)["counts"] == {"created": 0, "updated": 0, "reactivated": 0, "removed": 0},
              "events outside the window are not reported")
        check(build_change_summary(session, days=90)["counts"]["created"] == 3, "a wider window still sees them")
    finally:
        session.close()


def test_summary_api_endpoint() -> None:
    _reset()
    client = TestClient(api_main.app)
    response = client.get("/api/sync/summary")
    check(response.status_code == 200 and response.json()["tracking_available"] is False, response.text)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        repo.upsert_job_detailed(repo.get_or_create_company("Acme"), _data(1))
        session.commit()
    finally:
        session.close()
    body = client.get("/api/sync/summary", params={"days": 1}).json()
    check(body["counts"]["created"] == 1 and body["recent"][0]["title"] == "Engineer 1", f"{body}")
    check(client.get("/api/sync/summary", params={"days": 0}).status_code == 422, "days is validated")
    check(client.get("/api/sync/summary", params={"days": 365}).status_code == 422, "window is capped")


def test_scheduled_runner_reports_and_saves() -> None:
    _reset()
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        repo.upsert_job_detailed(repo.get_or_create_company("Acme"), _data(1))
        session.commit()
    finally:
        session.close()
    captured = {}
    original_dir = run_scheduled_sync.REPORT_DIR
    run_scheduled_sync.REPORT_DIR = Path(_TEMP_DIR.name) / "reports"
    try:
        with patch.object(run_scheduled_sync.sync_target_companies, "main", lambda argv: captured.setdefault("argv", argv) and 0):
            sys.argv = ["run_scheduled_sync.py", "--mode", "full", "--concurrency", "3", "--summary-days", "2"]
            code = run_scheduled_sync.main()
    finally:
        run_scheduled_sync.REPORT_DIR = original_dir
    check(code == 0, "runner returns the sync exit code")
    check(captured["argv"] == ["--mode", "full", "--concurrency", "3"], f"sync receives mode and concurrency: {captured}")
    reports = list((Path(_TEMP_DIR.name) / "reports").glob("sync_*.txt"))
    check(len(reports) == 1 and "New: 1" in reports[0].read_text(encoding="utf-8"), "summary file written with the counts")


TESTS = [
    ("Summary counts events once and respects the window", test_summary_counts_and_no_duplicate_events),
    ("GET /api/sync/summary", test_summary_api_endpoint),
    ("Scheduled runner syncs then saves a summary", test_scheduled_runner_reports_and_saves),
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
