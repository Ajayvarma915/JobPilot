"""Tests for source states, health recording, the health API and sync behaviour.

Uses a temporary SQLite file (JOBPILOT_DATABASE_PATH); never touches jobpilot.db.
"""
from __future__ import annotations

import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_source_health.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.api.main import app  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.db.models import SourceHealth  # noqa: E402
from app.services import source_health as sh  # noqa: E402
from scripts import sync_target_companies as sync_module  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _company(cid: str, *, status: str, verified: bool, provider: str | None = "lever", settings: bool = True) -> dict:
    integration: dict = {"status": status, "verified": verified}
    if provider:
        integration["provider"] = provider
    if settings:
        integration["settings"] = {"site": cid}
    return {"id": cid, "name": cid.title(), "priority": 1, "careers_url": f"https://{cid}.example/careers", "integration": integration}


def _reset_table() -> None:
    SourceHealth.__table__.drop(bind=engine, checkfirst=True)


def test_registry_state_mapping() -> None:
    check(sh.registry_state(_company("a", status="active", verified=True))[0] == sh.ACTIVE, "verified active -> active")
    check(sh.registry_state(_company("a", status="active", verified=False))[0] == sh.AWAITING_VALIDATION,
          "active without the verified flag must NOT be trusted")
    check(sh.registry_state(_company("a", status="configured_needs_live_validation", verified=False))[0] == sh.AWAITING_VALIDATION,
          "configured but unvalidated -> awaiting_validation")
    check(sh.registry_state(_company("a", status="configured", verified=False))[0] == sh.CONFIGURED, "plain configured")
    check(sh.registry_state(_company("a", status="official_career_page_only", verified=False, provider=None, settings=False))[0] == sh.DISCOVERED,
          "no connector -> discovered")
    check(sh.registry_state(_company("a", status="pending_ats_discovery", verified=False, provider=None, settings=False))[0] == sh.DISCOVERED,
          "pending ATS discovery -> discovered")
    check(sh.registry_state(_company("a", status="deprecated", verified=True))[0] == sh.DEPRECATED, "deprecated passes through")
    check(sh.registry_state(_company("a", status="reviewed", verified=True))[0] == sh.VERIFIED, "verified but not active")
    # A provider alone (no settings) is not a working connector.
    check(sh.registry_state(_company("a", status="active", verified=True, settings=False))[0] == sh.AWAITING_VALIDATION,
          "provider without settings is not a working connector")
    for state in (sh.CONFIGURED, sh.AWAITING_VALIDATION, sh.DISCOVERED, sh.VERIFIED):
        check(not sh.is_auto_sync_state(state), f"{state} must not enter automatic sync")
    check(sh.is_auto_sync_state(sh.ACTIVE), "only active enters automatic sync")


def test_real_registry_has_valid_states() -> None:
    companies = sh.load_registry_companies()
    states = Counter(sh.registry_state(company)[0] for company in companies)
    check(set(states) <= set(sh.STATES), f"Unknown state in registry: {states}")
    for company in companies:
        state = sh.registry_state(company)[0]
        integration = company.get("integration") or {}
        if state == sh.ACTIVE:
            check(integration.get("verified") is True, f"{company['id']} is active without verification")
    report = sh.build_health_report(companies)
    check(report["summary"]["total"] == len(companies), "Every registry company must be listed")
    check(report["summary"]["never_fetched"] == len(companies), "Without history nothing has been fetched")


def test_effective_state_only_downgrades() -> None:
    check(sh.effective_state(sh.ACTIVE, 0) == sh.ACTIVE, "healthy stays active")
    check(sh.effective_state(sh.ACTIVE, 1) == sh.TEMPORARILY_UNAVAILABLE, "one failure -> temporarily unavailable")
    check(sh.effective_state(sh.ACTIVE, 3) == sh.FAILED, "repeated failures -> failed")
    check(sh.effective_state(sh.AWAITING_VALIDATION, 5) == sh.AWAITING_VALIDATION, "unverified sources are never promoted or relabelled")
    check(sh.effective_state(sh.DISCOVERED, 0) == sh.DISCOVERED, "discovered stays discovered")


def test_record_fetch_history() -> None:
    _reset_table()
    session = SessionLocal()
    try:
        t1, t2, t3 = datetime(2026, 11, 13, 9), datetime(2026, 11, 13, 10), datetime(2026, 11, 13, 11)
        sh.record_fetch(session, company_id="x", company_name="X", provider="lever", success=True,
                        counts={"raw_jobs": 10, "unique_jobs": 9, "eligible_jobs": 4, "review_jobs": 1,
                                "jobs_with_description": 9, "detail_attempted": 3, "detail_succeeded": 2}, now=t1)
        session.commit()
        row = session.get(SourceHealth, "x")
        check(row.raw_jobs == 10 and row.unique_jobs == 9 and row.last_success_at == t1, "success recorded")
        check(row.last_enrichment_success_at == t1, "enrichment success time recorded")

        sh.record_fetch(session, company_id="x", company_name="X", provider="lever", success=False, error="HTTP 503", now=t2)
        session.commit()
        row = session.get(SourceHealth, "x")
        check(row.consecutive_failures == 1 and row.last_error == "HTTP 503" and row.last_failure_at == t2, "failure recorded")
        check(row.raw_jobs == 10 and row.last_success_at == t1, "last good counts survive a failure")

        sh.record_fetch(session, company_id="x", company_name="X", provider="lever", success=True,
                        counts={"raw_jobs": 12, "unique_jobs": 12, "eligible_jobs": 5, "review_jobs": 0}, now=t3)
        session.commit()
        row = session.get(SourceHealth, "x")
        check(row.consecutive_failures == 0 and row.last_error is None and row.raw_jobs == 12, "recovery resets failures")
        check(row.detail_attempted is None, "unreported enrichment stays NULL, not zero")
    finally:
        session.close()


def test_health_api() -> None:
    _reset_table()
    client = TestClient(app)
    response = client.get("/api/sources/health")
    check(response.status_code == 200, response.text)
    data = response.json()
    check(not inspect(engine).has_table("source_health"), "GET must not create the table (read-only)")
    check(data["summary"]["total"] == len(data["items"]) > 0, "all registry companies listed")
    check(all(item["never_fetched"] for item in data["items"]), "no history yet")
    check(data["summary"]["auto_sync_allowed"] == sum(1 for i in data["items"] if i["state"] == "active"), "summary matches items")

    # Record a failed fetch for a registry company that is currently active and re-read.
    active = next(item for item in data["items"] if item["state"] == "active")
    session = SessionLocal()
    try:
        sh.record_fetch(session, company_id=active["id"], company_name=active["name"], provider=active["provider"],
                        success=False, error="HTTP 500")
        session.commit()
    finally:
        session.close()
    after = {item["id"]: item for item in client.get("/api/sources/health").json()["items"]}
    check(after[active["id"]]["state"] == "temporarily_unavailable", "failure must downgrade an active source")
    check(after[active["id"]]["last_error"] == "HTTP 500", "error surfaced")
    others = [i for i in after.values() if i["id"] != active["id"]]
    check(all(i["never_fetched"] for i in others), "other companies unaffected")


class _FakeCollector:
    def __init__(self, jobs):
        self.jobs = jobs

    def collect(self):
        if isinstance(self.jobs, Exception):
            raise self.jobs
        return self.jobs


def _run_sync(argv: list[str], collectors: dict[str, object]) -> int:
    companies = [_company("good", status="active", verified=True), _company("bad", status="active", verified=True)]
    original = (sync_module.load_registry, sync_module._make_collector, sys.argv)
    sync_module.load_registry = lambda: {"candidate": {"experience_start_date": "2025-09-18"}, "companies": companies}
    sync_module._make_collector = lambda company: _FakeCollector(collectors[company["id"]])
    sys.argv = ["sync_target_companies.py", *argv]
    try:
        return sync_module.main()
    finally:
        sync_module.load_registry, sync_module._make_collector, sys.argv = original


def test_sync_records_health_safely() -> None:
    jobs = [
        {"external_id": "1", "title": "Software Engineer", "url": "https://good.example/1", "location": ["Hyderabad, India"],
         "description": "Minimum qualifications: 1 year of experience.", "_jobpilot_detail_fetch_status": "fetched"},
        {"external_id": "1", "title": "Software Engineer", "url": "https://good.example/1", "location": ["Hyderabad, India"],
         "description": "Minimum qualifications: 1 year of experience.", "_jobpilot_detail_fetch_status": "failed"},
        {"external_id": "2", "title": "Account Executive", "url": "https://good.example/2", "location": ["Mumbai, India"], "description": ""},
    ]
    collectors = {"good": jobs, "bad": RuntimeError("HTTP 500 from source")}

    # 1. Plain dry run must not write anything to the database.
    _reset_table()
    code = _run_sync(["--dry-run"], collectors)
    check(code == 1, "A failing company makes the run exit non-zero")
    check(not inspect(engine).has_table("source_health"), "Plain dry run must not create or write source_health")

    # 2. Dry run with --record-health records both, and one failure does not stop the other.
    code = _run_sync(["--dry-run", "--record-health"], collectors)
    session = SessionLocal()
    try:
        good, bad = session.get(SourceHealth, "good"), session.get(SourceHealth, "bad")
        check(good is not None and bad is not None, "Both companies recorded; failure did not stop the loop")
        check(good.raw_jobs == 3 and good.unique_jobs == 2, f"raw/unique counts wrong: {good.raw_jobs}/{good.unique_jobs}")
        check(good.eligible_jobs == 2 and good.review_jobs is not None, "software roles counted as eligible, Account Executive excluded")
        check(good.jobs_with_description == 2, "description completeness counted")
        check(good.detail_attempted == 2 and good.detail_succeeded == 1, "detail enrichment counts from connector status")
        check(good.consecutive_failures == 0 and good.last_success_at is not None, "good source marked successful")
        check(bad.consecutive_failures == 1 and "HTTP 500" in (bad.last_error or ""), "bad source failure recorded")
    finally:
        session.close()


TESTS = [
    ("Registry entries map to explicit states", test_registry_state_mapping),
    ("Real registry has valid, never-overtrusted states", test_real_registry_has_valid_states),
    ("Effective state only downgrades", test_effective_state_only_downgrades),
    ("Fetch history recorded and recovered", test_record_fetch_history),
    ("GET /api/sources/health is read-only and merges history", test_health_api),
    ("Sync records health; dry run is read-only by default", test_sync_records_health_safely),
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
    api_main.engine.dispose()  # main.py builds its own engine on the same file
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
