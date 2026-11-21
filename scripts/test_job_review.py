"""Tests for jobs held for review: stored by the sync, hidden from the normal list, decided by the user.

Uses a temporary database and a fake source. No network and no real data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_job_review.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.models import Job, JobReview, JobVersion  # noqa: E402
from scripts import sync_target_companies as sync  # noqa: E402

STATED = "Minimum qualifications: 1 year of software development experience. Build backend services in Python."
UNSTATED = "Build backend services in Python and work with a friendly team on cloud systems every day."

COMPANY = {
    "id": "acme", "name": "Acme", "website": "https://acme.example", "careers_url": "https://acme.example/careers",
    "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": "acme"}},
}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeCollector:
    def __init__(self, jobs):
        self.jobs = jobs

    def collect(self):
        return [dict(job) for job in self.jobs]


def posting(key: str, description: str, title: str = "Software Engineer", location: str = "Pune, India") -> dict:
    return {"external_id": key, "title": f"{title} {key}", "url": f"https://acme.example/{key}", "source": "lever:acme",
            "location": [location], "description": description}


def run_sync(jobs, company=COMPANY):
    original = sync._build_collector
    sync._build_collector = lambda c, **kwargs: FakeCollector(jobs)
    try:
        return sync.sync_company(company, dry_run=False, maximum_required_years=2.0)
    finally:
        sync._build_collector = original


def titles(client, scope):
    body = client.get("/api/jobs", params={"review_scope": scope, "location": "India", "limit": 100}).json()
    return {item["title"]: item for item in body["items"]}


def fresh_client() -> TestClient:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(api_main.app)


def test_sync_stores_ambiguous_jobs_for_review() -> None:
    client = fresh_client()
    result = run_sync([posting("a1", STATED), posting("b1", UNSTATED)])
    check(result.inserted == 2 and result.stored_for_review == 1, f"both stored, one held: {result}")
    main, review = titles(client, "main"), titles(client, "review")
    check(list(main) == ["Software Engineer a1"], f"the normal list shows only the clean job: {list(main)}")
    check(list(review) == ["Software Engineer b1"], f"the review tab shows the held job: {list(review)}")
    held = review["Software Engineer b1"]["review"]
    check(held["status"] == "pending" and "minimum_experience_not_found_review" in held["flags"], held)
    check(held["reasons"] and "years of experience" in held["reasons"][0], f"reasons are readable: {held}")
    check(main["Software Engineer a1"]["review"] is None, "a clean job carries no review")
    stats = client.get("/api/dashboard/stats").json()
    check(stats["active_jobs"] == 1 and stats["needs_review_jobs"] == 1, f"dashboard counts split: {stats}")


def test_decisions_are_kept_across_syncs() -> None:
    client = fresh_client()
    run_sync([posting("a1", STATED), posting("b1", UNSTATED), posting("c1", UNSTATED)])
    session = SessionLocal()
    try:
        ids = {job.external_id: job.id for job in session.query(Job).all()}
    finally:
        session.close()

    check(client.post(f"/api/jobs/{ids['b1']}/review-decision", json={"decision": "accept"}).json()["review"]["status"] == "accepted", "accept")
    check(client.post(f"/api/jobs/{ids['c1']}/review-decision", json={"decision": "dismiss"}).json()["review"]["status"] == "dismissed", "dismiss")
    check(client.post(f"/api/jobs/{ids['a1']}/review-decision", json={"decision": "accept"}).status_code == 404, "a clean job has nothing to decide")
    check(client.post(f"/api/jobs/{ids['b1']}/review-decision", json={"decision": "nonsense"}).status_code == 422, "bad decision rejected")

    check(set(titles(client, "main")) == {"Software Engineer a1", "Software Engineer b1"}, "an accepted job joins the normal list")
    check(not titles(client, "review"), "nothing is left waiting")
    check(set(titles(client, "dismissed")) == {"Software Engineer c1"}, "a dismissed job is only in the dismissed tab")
    check("Software Engineer c1" not in titles(client, "main"), "a dismissed job is hidden from the normal list")

    run_sync([posting("a1", STATED), posting("b1", UNSTATED), posting("c1", UNSTATED)])  # the next sync must not undo decisions
    check(set(titles(client, "main")) == {"Software Engineer a1", "Software Engineer b1"}, "decisions survive the next sync")
    check(set(titles(client, "dismissed")) == {"Software Engineer c1"}, "dismissal survives the next sync")

    check(client.post(f"/api/jobs/{ids['c1']}/review-decision", json={"decision": "reset"}).json()["review"]["status"] == "pending", "reset")
    check(set(titles(client, "review")) == {"Software Engineer c1"}, "a reset job waits for review again")


def test_job_that_becomes_clear_leaves_the_queue_and_closed_jobs_still_close() -> None:
    client = fresh_client()
    run_sync([posting("b1", UNSTATED), posting("d1", STATED), posting("e1", STATED)])
    check(set(titles(client, "review")) == {"Software Engineer b1"}, "held at first")
    result = run_sync([posting("b1", STATED), posting("d1", STATED)])  # b1 now states its years; e1 is gone
    check(not titles(client, "review") and "Software Engineer b1" in titles(client, "main"), "once clear, it joins the normal list")
    check(result.removed == 1 and "Software Engineer e1" not in titles(client, "main"), f"removal detection still works: {result}")
    session = SessionLocal()
    try:
        check(session.query(JobReview).count() == 0, "no stale review rows remain")
    finally:
        session.close()


def test_unverified_sources_never_store_review_jobs() -> None:
    client = fresh_client()
    pending = {**COMPANY, "integration": {**COMPANY["integration"], "status": "awaiting_validation", "verified": False}}
    result = run_sync([posting("b1", UNSTATED)], pending)
    check(result.inserted == 0 and not titles(client, "review") and not titles(client, "main"), f"nothing is written: {result}")


def test_older_database_without_the_new_tables() -> None:
    """Regression: a sandbox sync on a pre-existing database failed with 'database is locked'
    because the new tables were created in the middle of a write."""
    client = fresh_client()
    JobReview.__table__.drop(bind=engine)
    JobVersion.__table__.drop(bind=engine)
    result = run_sync([posting("a1", STATED), posting("b1", UNSTATED)])
    check(result.status == "success" and result.inserted == 2, f"sync works on an older database: {result}")
    check(list(titles(client, "review")) == ["Software Engineer b1"], "review queue works after the tables were added")
    JobReview.__table__.drop(bind=engine)
    check(client.get("/api/jobs", params={"location": "India"}).status_code == 200, "the API recreates a missing table")


def test_india_filter_sees_city_and_code_locations() -> None:
    """Regression: Amazon ("IN, TS, Hyderabad") and CRED ("bengaluru") were stored but invisible
    to the default India filter, which only matched the literal word India."""
    client = fresh_client()
    run_sync([posting("a1", STATED, location="IN, TS, Hyderabad"), posting("b1", STATED, location="bengaluru"),
              posting("c1", STATED, location="US, WA, Seattle")])
    shown = set(titles(client, "main"))
    check(shown == {"Software Engineer a1", "Software Engineer b1"}, f"India cities and codes are found, Seattle is not: {shown}")


def test_remote_jobs_have_their_own_section() -> None:
    client = fresh_client()
    run_sync([posting("a1", STATED, location="Pune, India"),
              posting("r1", STATED, location="Remote - India"),
              posting("r2", STATED, location="Remote"),
              posting("r3", STATED, location="Remote US"),
              posting("h1", STATED, location="Remote; Pune, India")])
    main, remote = set(titles(client, "main")), titles(client, "remote")
    check(main == {"Software Engineer a1", "Software Engineer h1"}, f"office and hybrid jobs only in the main list: {main}")
    check(set(remote) == {"Software Engineer r1", "Software Engineer r2"}, f"remote-only jobs in the remote section, not Remote US: {set(remote)}")
    check(remote["Software Engineer r2"]["review"]["status"] == "pending", "a plain Remote job still shows why it needs a check")
    check(not any(t.startswith("Software Engineer r") for t in titles(client, "review")), "remote jobs are not duplicated in the review tab")
    session = SessionLocal()
    try:
        rid = session.query(Job).filter(Job.external_id == "r2").one().id
    finally:
        session.close()
    client.post(f"/api/jobs/{rid}/review-decision", json={"decision": "dismiss"})
    check("Software Engineer r2" not in titles(client, "remote"), "a dismissed remote job is hidden")


def test_new_jobs_are_marked_and_filterable() -> None:
    from datetime import datetime, timedelta

    client = fresh_client()
    run_sync([posting("a1", STATED), posting("b1", STATED)])
    session = SessionLocal()
    try:
        old = session.query(Job).filter(Job.external_id == "b1").one()
        old.first_seen_at = datetime.utcnow() - timedelta(days=10)
        session.commit()
    finally:
        session.close()
    everything = client.get("/api/jobs", params={"location": "India", "limit": 50}).json()["items"]
    flags = {item["title"]: item["is_new"] for item in everything}
    check(flags == {"Software Engineer a1": True, "Software Engineer b1": False}, flags)
    only_new = client.get("/api/jobs", params={"location": "India", "limit": 50, "new_only": "true"}).json()["items"]
    check([item["title"] for item in only_new] == ["Software Engineer a1"], "only the job first seen this week")


TESTS = [
    ("Sync stores ambiguous jobs and the API separates them", test_sync_stores_ambiguous_jobs_for_review),
    ("Accept, dismiss and reset are kept across syncs", test_decisions_are_kept_across_syncs),
    ("A job that becomes clear leaves the queue; removal still works", test_job_that_becomes_clear_leaves_the_queue_and_closed_jobs_still_close),
    ("Unverified sources store nothing", test_unverified_sources_never_store_review_jobs),
    ("Remote jobs have their own section", test_remote_jobs_have_their_own_section),
    ("New jobs are marked and can be filtered", test_new_jobs_are_marked_and_filterable),
    ("The India filter finds city names and country codes", test_india_filter_sees_city_and_code_locations),
    ("An older database without the new tables syncs without locking", test_older_database_without_the_new_tables),
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
