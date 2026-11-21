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
from app.services.job_status import CLOSED, OPEN, UNKNOWN, classify_google_page, classify_job_page, decide, list_only  # noqa: E402
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
        return [{"source": "lever:acme", **job} for job in self.jobs]


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
    original_page_get = api_main._page_get
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

        # no connector: the job's own page is read instead (nothing here may reach the network, so it is faked)
        from app.services import job_import
        real_dns = job_import.socket.getaddrinfo
        job_import.socket.getaddrinfo = lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))]
        api_main._page_get = lambda url, **kw: type("R", (), {"status_code": 200, "text": "<html>An unrelated page</html>"})()
        no_connector = client.post(f"/api/jobs/{ids['n']}/verify-open").json()
        check(no_connector["status"] == "unknown" and "did not clearly show" in no_connector["reason"], no_connector)
        job_import.socket.getaddrinfo = real_dns
        # Google: read the job's own page. The link in this test is not a Google page, so nothing is fetched.
        google = client.post(f"/api/jobs/{ids['g']}/verify-open").json()
        check(google["status"] == "unknown" and "not a Google careers page" in google["reason"], google)
        check(client.post("/api/jobs/99999/verify-open").status_code == 404, "unknown job -> 404")
    finally:
        api_main.load_registry_companies, sync._build_collector = original
        api_main._page_get = original_page_get


def test_google_page_rules() -> None:
    gone = "<h1>Job not found.</h1><p>This job may have been taken down.</p>"
    check(classify_google_page(200, gone)[0] == CLOSED, "the taken-down page closes the job")
    check(classify_google_page(200, "<h2>Responsibilities</h2> Build things")[0] == OPEN, "a page with its responsibilities is open")
    check(classify_google_page(404, "")[0] == CLOSED, "a 404 means the page is gone")
    check(classify_google_page(503, "")[0] == UNKNOWN and classify_google_page(200, "<html>captcha</html>")[0] == UNKNOWN,
          "errors and unclear pages change nothing")


def test_job_from_a_remote_board_is_checked_on_that_board() -> None:
    """Regression: a GitLab job saved from We Work Remotely was checked against GitLab's own Greenhouse board,
    where it is never listed, so it always came back 'closed' (even right after an update)."""
    from app.collectors import remote_boards

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        gitlab = repo.get_or_create_company("GitLab")
        ids = {}
        for key in ("w1", "w2", "w3"):
            ids[key] = repo.upsert_job_detailed(gitlab, {"source": "remote_board:weworkremotely", "external_id": f"weworkremotely-{key}",
                                                         "title": f"Backend Engineer {key}", "location": ["Remote - Worldwide"],
                                                         "url": f"https://wwr.example/{key}", "description": "Build things."}).job.id
        session.commit()
    finally:
        session.close()

    registry = [{"id": "gitlab", "name": "GitLab", "integration": {"provider": "greenhouse", "status": "active", "verified": True, "settings": {"board": "gitlab"}}}]
    original = (api_main.load_registry_companies, sync._build_collector, dict(remote_boards.COLLECTORS))
    api_main.load_registry_companies = lambda: registry

    def company_connector_must_not_be_used(company, **kwargs):
        raise AssertionError("a remote-board job must never be checked against the company's own connector")

    sync._build_collector = company_connector_must_not_be_used

    class FakeBoard:
        source = "remote_board:weworkremotely"

        def __init__(self, listed):
            self.listed = listed

        def collect(self):
            if isinstance(self.listed, Exception):
                raise self.listed
            return [{"external_id": f"weworkremotely-{key}"} for key in self.listed]

    def board_lists(listed):
        remote_boards.COLLECTORS["weworkremotely"] = lambda **kwargs: FakeBoard(listed)

    client = TestClient(api_main.app)
    try:
        board_lists(["w1", "w2", "w3"])
        listed = client.post(f"/api/jobs/{ids['w1']}/verify-open").json()
        check(listed["status"] == "open" and "weworkremotely" in listed["reason"], f"still on the board -> open: {listed}")
        board_lists(["w2", "w3"])
        gone = client.post(f"/api/jobs/{ids['w1']}/verify-open").json()
        check(gone["status"] == "closed" and not gone["is_active"], f"gone from a normal board answer -> closed: {gone}")
        board_lists([])
        check(client.post(f"/api/jobs/{ids['w2']}/verify-open").json()["status"] == "unknown", "an empty board answer closes nothing")
        board_lists(RuntimeError("HTTP 503"))
        failed = client.post(f"/api/jobs/{ids['w2']}/verify-open").json()
        check(failed["status"] == "unknown" and "503" in failed["reason"], failed)
    finally:
        api_main.load_registry_companies, sync._build_collector = original[0], original[1]
        remote_boards.COLLECTORS.clear()
        remote_boards.COLLECTORS.update(original[2])


def test_page_check_for_saved_links() -> None:
    check(classify_job_page(404, "", "Engineer")[0] == CLOSED, "a missing page means closed")
    check(classify_job_page(200, "<h1>Backend Engineer</h1> Apply now", "Backend Engineer")[0] == OPEN, "the title is still on the page")
    check(classify_job_page(200, "Sorry, this job is no longer available. Backend Engineer", "Backend Engineer")[0] == CLOSED, "an explicit closed notice wins")
    check(classify_job_page(200, "Welcome to our careers site", "Backend Engineer")[0] == UNKNOWN, "an unrelated page proves nothing")
    check(classify_job_page(503, "", "x")[0] == UNKNOWN and classify_job_page(200, "", "")[0] == UNKNOWN, "errors and empty pages change nothing")


TESTS = [
    ("Google page rules", test_google_page_rules),
    ("A job from a remote board is checked on that board, not the company's page", test_job_from_a_remote_board_is_checked_on_that_board),
    ("A saved link is checked from its own page", test_page_check_for_saved_links),
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
