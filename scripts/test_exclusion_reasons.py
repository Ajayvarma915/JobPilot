"""Tests for the "why are there no jobs from this company" breakdown (temp database, fake jobs)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_exclusions.db")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal, engine  # noqa: E402
from app.services.source_health import (  # noqa: E402
    build_health_report, describe_exclusions, ensure_source_health_table, load_health_rows, record_fetch,
)
from scripts import sync_target_companies as sync  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_grouping_is_short_and_ordered() -> None:
    result = describe_exclusions({"senior_or_lead_title": 10, "requires_3_years": 4, "requires_5_years": 3, "non_software_title": 7,
                                  "outside_india": 1, "phd_required_or_phd_targeted_title": 1, "internship_or_trainee": 2}, limit=3)
    check([r["label"] for r in result] == ["senior, staff or lead titles", "ask for more experience than your limit", "not software roles"], result)
    check(result[1]["count"] == 7, "the 3-, 4- and 5-year reasons are added together")
    check(describe_exclusions(None) == [], "nothing recorded -> nothing to explain")


def test_old_table_gains_the_column_and_reports_reasons() -> None:
    with engine.begin() as connection:  # the table as an older version of the app created it
        connection.execute(text("CREATE TABLE source_health (company_id VARCHAR(100) PRIMARY KEY, company_name VARCHAR(255) NOT NULL, "
                                "provider VARCHAR(100), last_attempt_at DATETIME, last_success_at DATETIME, last_failure_at DATETIME, "
                                "last_error TEXT, consecutive_failures INTEGER NOT NULL DEFAULT 0, raw_jobs INTEGER, unique_jobs INTEGER, "
                                "eligible_jobs INTEGER, review_jobs INTEGER, jobs_with_description INTEGER, detail_attempted INTEGER, "
                                "detail_succeeded INTEGER, last_enrichment_success_at DATETIME, pagination_status VARCHAR(50) NOT NULL DEFAULT 'not_reported', "
                                "updated_at DATETIME NOT NULL)"))
    session = SessionLocal()
    try:
        ensure_source_health_table(session)
        record_fetch(session, company_id="acme", company_name="Acme", provider="lever", success=True,
                     counts={"raw_jobs": 12}, exclusion_reasons={"senior_or_lead_title": 9, "non_software_title": 3})
        session.commit()
        companies = [{"id": "acme", "name": "Acme", "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": "a"}}}]
        item = build_health_report(companies, load_health_rows(session))["items"][0]
        check(item["why_excluded"][0] == {"label": "senior, staff or lead titles", "count": 9}, item["why_excluded"])
        # a later failed fetch keeps the last good explanation
        record_fetch(session, company_id="acme", company_name="Acme", provider="lever", success=False, error="HTTP 503")
        session.commit()
        item = build_health_report(companies, load_health_rows(session))["items"][0]
        check(item["why_excluded"] and item["consecutive_failures"] == 1, item)
    finally:
        session.close()


def test_api_reads_an_older_health_table_without_losing_companies() -> None:
    """Regression: with an older source_health table the health and coverage endpoints failed or silently
    dropped every company that had no jobs yet (found while checking the sandbox copy)."""
    from fastapi.testclient import TestClient

    from app.api import main as api_main
    from app.db.database import Base

    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS source_health"))
        connection.execute(text("CREATE TABLE source_health (company_id VARCHAR(100) PRIMARY KEY, company_name VARCHAR(255) NOT NULL, "
                                "provider VARCHAR(100), last_attempt_at DATETIME, last_success_at DATETIME, last_failure_at DATETIME, "
                                "last_error TEXT, consecutive_failures INTEGER NOT NULL DEFAULT 0, raw_jobs INTEGER, unique_jobs INTEGER, "
                                "eligible_jobs INTEGER, review_jobs INTEGER, jobs_with_description INTEGER, detail_attempted INTEGER, "
                                "detail_succeeded INTEGER, last_enrichment_success_at DATETIME, pagination_status VARCHAR(50) NOT NULL DEFAULT 'not_reported', "
                                "updated_at DATETIME NOT NULL)"))
        connection.execute(text("INSERT INTO source_health (company_id, company_name, raw_jobs, updated_at) VALUES ('google', 'Google', 173, '2026-11-19')"))
    client = TestClient(api_main.app)
    health = client.get("/api/sources/health")
    check(health.status_code == 200 and len(health.json()["items"]) >= 30, f"health endpoint: {health.status_code}")
    coverage = client.get("/api/companies/coverage").json()["items"]
    check(len(coverage) >= 30, f"every registry company is listed even with no jobs: {len(coverage)}")
    names = {item["name"] for item in coverage}
    check({"Adobe", "Microsoft", "Qualcomm"} <= names, "companies with no jobs are still there")


def test_sync_counts_the_reasons() -> None:
    company = {"id": "demo", "name": "Demo", "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": "demo"}}}
    stated = "Minimum qualifications: 1 year of software development experience."
    jobs = [
        {"external_id": "1", "title": "Software Engineer", "url": "https://d/1", "location": ["Pune, India"], "description": stated},
        {"external_id": "2", "title": "Senior Software Engineer", "url": "https://d/2", "location": ["Pune, India"], "description": stated},
        {"external_id": "3", "title": "Staff Software Engineer", "url": "https://d/3", "location": ["Pune, India"], "description": stated},
        {"external_id": "4", "title": "Account Executive", "url": "https://d/4", "location": ["Pune, India"], "description": stated},
        {"external_id": "5", "title": "Software Engineer", "url": "https://d/5", "location": ["Seattle, WA"], "description": stated},
        {"external_id": "6", "title": "Software Engineer", "url": "https://d/6", "location": ["Pune, India"],
         "description": "Minimum qualifications: 6 years of experience."},
    ]
    result = sync.sync_company(company, dry_run=True, maximum_required_years=2.0, prefetched_jobs=jobs)
    check(result.exclusions == {"senior_or_lead_title": 2, "non_software_title": 1, "location_not_verified_as_india": 1, "requires_6_years": 1}, result.exclusions)
    check(result.eligible == 1, "one job fits")


TESTS = [
    ("Reason codes are grouped into short labels", test_grouping_is_short_and_ordered),
    ("An older table gains the column and reports reasons", test_old_table_gains_the_column_and_reports_reasons),
    ("The API reads an older health table without losing companies", test_api_reads_an_older_health_table_without_losing_companies),
    ("The sync counts why jobs were dropped", test_sync_counts_the_reasons),
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
    if "app.api.main" in sys.modules:
        sys.modules["app.api.main"].engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
