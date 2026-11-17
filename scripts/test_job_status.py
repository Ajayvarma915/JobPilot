"""Tests for the on-demand 'is this job still open?' check (temp DB, fake sources, no network)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_job_status.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.db.models import Job, JobVersion  # noqa: E402
from app.services.job_status import CLOSED, OPEN, UNKNOWN, decide, list_only  # noqa: E402
from scripts import sync_target_companies as sync  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_decision_rules() -> None:
    check(decide(external_id="1", fetched_ids={"1", "2"}, stored_active_count=2)[0] == OPEN, "listed -> open")
    check(decide(external_id="3", fetched_ids={"1", "2"}, stored_active_count=3)[0] == CLOSED, "gone from a normal answer -> closed")
    check(decide(external_id="3", fetched_ids=set(), stored_active_count=3)[0] == UNKNOWN, "an empty answer closes nothing")
    check(decide(external_id="3", fetched_ids={"1"}, stored_active_count=10)[0] == UNKNOWN, "a suspiciously small answer closes nothing")
    check(decide(external_id=None, fetched_ids={"1"}, stored_active_count=1)[0] == UNKNOWN, "no id -> unknown")
    for status, reason in (decide(external_id="3", fetched_ids={"1"}, stored_active_count=10), decide(external_id="9", fetched_ids={"1", "2"}, stored_active_count=2)):
        check(reason, "every answer explains itself")
    entry = {"integration": {"provider": "workday", "settings": {"fetch_details": True, "tenant": "t"}}}
    check(list_only(entry)["integration"]["settings"]["fetch_details"] is False and entry["integration"]["settings"]["fetch_details"] is True,
          "the check skips per-job detail requests without changing the registry entry")


class FakeCollector:
    def __init__(self, jobs):
        self.jobs = jobs

    def collect(self):
        if isinstance(self.jobs, Exception):
            raise self.jobs
        return self.jobs


def test_endpoint_updates_jobs_only_when_sure() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        acme = repo.get_or_create_company("Acme")
        nocon = repo.get_or_create_company("NoConnector")
        goog = repo.get_or_create_company("Google")
        ids = {}
        for key, company, source in (("a", acme, "lever:acme"), ("b", acme, "lever:acme"), ("c", acme, "lever:acme"),
                                     ("n", nocon, "x"), ("g", goog, "google_careers")):
            ids[key] = repo.upsert_job_detailed(company, {"source": source, "external_id": key, "title": f"Engineer {key}",
                                                           "location": ["Pune, India"], "url": f"https://x.example/{key}",
                                                           "description": "Minimum qualifications: 1 year."}).job.id
        session.commit()
    finally:
        session.close()

    registry = [
        {"id": "acme", "name": "Acme", "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": "acme"}}},
        {"id": "nocon", "name": "NoConnector", "integration": {"status": "pending_ats_discovery"}},
        {"id": "google", "name": "Google", "integration": {"provider": "google_careers", "status": "active", "verified": True, "settings": {"queries": ["x"]}}},
    ]
    original = (api_main.load_registry_companies, sync._build_collector)
    api_main.load_registry_companies = lambda: registry
    client = TestClient(api_main.app)

    def serve(jobs):
        sync._build_collector = lambda company, **kwargs: FakeCollector(jobs)

    def state(key):
        s = SessionLocal()
        try:
            job = s.get(Job, ids[key])
            versions = [v.change_type for v in s.scalars(select(JobVersion).where(JobVersion.job_id == job.id).order_by(JobVersion.version_no))]
            return job.is_active, job.last_seen_at, versions
        finally:
            s.close()

    try:
        before = state("a")[1]
        serve([{"external_id": "a"}, {"external_id": "b"}, {"external_id": "c"}])
        opened = client.post(f"/api/jobs/{ids['a']}/verify-open").json()
        check(opened["status"] == "open" and opened["is_active"] and state("a")[1] > before, f"open refreshes the confirmed time: {opened}")

        serve([{"external_id": "a"}, {"external_id": "b"}])  # c is gone from a normal answer
        closed = client.post(f"/api/jobs/{ids['c']}/verify-open").json()
        active, _, versions = state("c")
        check(closed["status"] == "closed" and not active and not closed["is_active"] and versions[-1] == "removed", f"closed: {closed}")
        check(state("a")[0] and state("b")[0], "other jobs are untouched when one is closed")

        serve([{"external_id": "a"}, {"external_id": "b"}, {"external_id": "c"}])  # re-posted
        again = client.post(f"/api/jobs/{ids['c']}/verify-open").json()
        check(again["status"] == "open" and state("c")[0] and state("c")[2][-1] == "reactivated", f"a re-listed job is reactivated: {again}")

        serve(RuntimeError("HTTP 503"))
        failed = client.post(f"/api/jobs/{ids['a']}/verify-open").json()
        check(failed["status"] == "unknown" and state("a")[0] and "503" in failed["reason"], f"a failing source leaves the job untouched: {failed}")
        serve([])
        check(client.post(f"/api/jobs/{ids['a']}/verify-open").json()["status"] == "unknown" and state("a")[0], "an empty answer leaves the job untouched")
        serve([{"external_id": "a"}])  # 1 of 3 stored: looks partial
        partial = client.post(f"/api/jobs/{ids['b']}/verify-open").json()
        check(partial["status"] == "unknown" and state("b")[0] and "partial" in partial["reason"], f"a partial answer closes nothing: {partial}")

        no_connector = client.post(f"/api/jobs/{ids['n']}/verify-open").json()
        check(no_connector["status"] == "unknown" and "no connector" in no_connector["reason"].lower(), no_connector)
        google = client.post(f"/api/jobs/{ids['g']}/verify-open").json()
        check(google["status"] == "unknown" and "full sync" in google["reason"], google)
        check(client.post("/api/jobs/99999/verify-open").status_code == 404, "unknown job -> 404")
    finally:
        api_main.load_registry_companies, sync._build_collector = original


TESTS = [
    ("Decision rules never close a job on doubt", test_decision_rules),
    ("Endpoint closes, reopens and leaves doubtful jobs alone", test_endpoint_updates_jobs_only_when_sure),
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
