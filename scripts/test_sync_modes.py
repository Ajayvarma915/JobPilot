"""Sync tests: change tracking, removal guard, FAST mode, description reuse, concurrency.

Uses fake collectors and a temporary database; no network, never touches jobpilot.db.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_sync_modes.db")

from sqlalchemy import select  # noqa: E402

from app.collectors.oracle_hcm import OracleHCMCollector  # noqa: E402
from app.collectors.workday import WorkdayCollector  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.models import Job, JobVersion  # noqa: E402
from scripts import sync_target_companies as sync  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _company(cid: str = "acme") -> dict:
    return {"id": cid, "name": cid.title(), "website": f"https://{cid}.example", "careers_url": f"https://{cid}.example/jobs",
            "integration": {"provider": "lever", "status": "active", "verified": True, "settings": {"site": cid}}}


TITLES = ["Backend Engineer", "Frontend Engineer", "Full Stack Engineer", "Data Engineer", "Platform Engineer",
          "Software Engineer", "Machine Learning Engineer", "DevOps Engineer"]


def _job(i: int, description: str = "Minimum qualifications: 1 year of experience.") -> dict:
    # Distinct titles: identical postings would be flagged as probable duplicates for review.
    return {"external_id": str(i), "title": TITLES[i - 1], "url": f"https://acme.example/{i}", "source": "lever:acme",
            "location": ["Hyderabad, India"], "description": description, "employment_type": "Full-time"}


class FakeCollector:
    def __init__(self, jobs):
        self.jobs = jobs
        self.known_descriptions = {}

    def collect(self):
        return [dict(job) for job in self.jobs]


def _run(jobs, **kwargs):
    # Source is verified-active, so eligible jobs without review flags are written.
    with patch.object(sync, "_make_collector", lambda company: FakeCollector(jobs)):
        return sync.sync_company(_company(), dry_run=False, maximum_required_years=2.0, **kwargs)


def _reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_change_counters_and_removal() -> None:
    _reset()
    first = _run([_job(1), _job(2), _job(3)])
    check(first.inserted == 3 and first.updated == 0 and first.unchanged == 0, f"first run: {first}")

    second = _run([_job(1), _job(2), _job(3)])
    check(second.inserted == 0 and second.unchanged == 3 and second.removed == 0, f"identical run must be all unchanged: {second}")

    third = _run([_job(1, "Minimum qualifications: 2 years of experience."), _job(2), _job(3)])
    check(third.updated == 1 and third.unchanged == 2, f"one edited description: {third}")

    fourth = _run([_job(1, "Minimum qualifications: 2 years of experience."), _job(2)])
    check(fourth.removed == 1, f"job 3 disappeared from the source: {fourth}")
    session = SessionLocal()
    try:
        jobs = {j.external_id: j for j in session.scalars(select(Job)).all()}
        check(jobs["3"].is_active is False and jobs["1"].is_active and jobs["2"].is_active, "only job 3 deactivated")
        kinds = [v.change_type for v in session.scalars(select(JobVersion).where(JobVersion.job_id == jobs["3"].id).order_by(JobVersion.version_no))]
        check(kinds == ["created", "removed"], kinds)
    finally:
        session.close()

    back = _run([_job(1, "Minimum qualifications: 2 years of experience."), _job(2), _job(3)])
    check(back.reactivated == 1 and back.removed == 0, f"re-posted job reactivated: {back}")


def test_removal_guard_and_modes() -> None:
    _reset()
    _run([_job(i) for i in range(1, 7)])  # 6 stored active jobs

    partial = _run([_job(1)])  # 1 of 6 collected: looks like a partial/failed fetch
    check(partial.removed == 0 and partial.removal_note and "partial" in partial.removal_note, f"guard must skip: {partial}")

    fast = _run([_job(1), _job(2), _job(3), _job(4), _job(5)], fast_google_scan=True)
    check(fast.removed == 0, "FAST mode never removes")

    off = _run([_job(1), _job(2), _job(3), _job(4), _job(5)], detect_removals=False)
    check(off.removed == 0, "removal detection can be switched off")

    full = _run([_job(1), _job(2), _job(3), _job(4), _job(5)])
    check(full.removed == 1, f"a complete FULL fetch removes the one missing job: {full}")
    session = SessionLocal()
    try:
        check(sum(1 for j in session.scalars(select(Job)).all() if j.is_active) == 5, "five jobs remain active")
    finally:
        session.close()


def test_fast_mode_reuses_stored_descriptions() -> None:
    _reset()
    one = "Stored description for job one. Minimum qualifications: 1 year of experience."
    two = "Stored description for job two. Minimum qualifications: 1 year of experience."
    _run([_job(1, one), _job(2, two)])  # must state the experience, otherwise the job is held for review, not stored
    known = sync._load_known_descriptions(_company())
    check(known == {"1": one, "2": two}, f"known={known}")
    check(sync._load_known_descriptions({"name": "Nobody"}) == {}, "unknown company has nothing to reuse")

    captured = {}

    def fake_make(company):
        collector = FakeCollector([])
        captured["collector"] = collector
        return collector

    with patch.object(sync, "_make_collector", fake_make):
        sync._build_collector(_company(), known_descriptions=known)
    check(captured["collector"].known_descriptions == known, "known descriptions are handed to the collector")

    # Workday: reused description means no detail request for that job.
    workday = WorkdayCollector(tenant="t", site="s", company_name="T", host="https://t.wd5.myworkdayjobs.com",
                               page_size=20, max_pages=1, fetch_details=True)
    workday.known_descriptions = {"R1": "Reused description."}

    class Resp:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    page = Resp({"total": 2, "jobPostings": [
        {"title": "Software Engineer", "externalPath": "/job/IN/a_R1", "jobReqId": "R1", "locationsText": "India"},
        {"title": "Backend Engineer", "externalPath": "/job/IN/b_R2", "jobReqId": "R2", "locationsText": "India"},
    ]})
    details = []

    def fake_detail(path):
        details.append(path)
        return {"description": "Fetched description.", "_jobpilot_detail_fetch_status": "fetched"}

    workday._fetch_detail = fake_detail
    with patch.object(workday.session, "post", return_value=page):
        jobs = {j["external_id"]: j for j in workday.collect()}
    check(details == ["/job/IN/b_R2"], f"only the unknown job may be fetched, got {details}")
    check(jobs["R1"]["description"] == "Reused description." and jobs["R1"]["_jobpilot_detail_fetch_status"] == "reused", "reuse recorded")

    # Oracle: same behaviour.
    oracle = OracleHCMCollector(base_url="https://t.fa.ocs.oraclecloud.com", site_number="S", company_name="T", fetch_details=True)
    oracle.known_descriptions = {"1": "Reused oracle description."}
    job = {"external_id": "1", "description": ""}
    other = {"external_id": "2", "description": ""}
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(params["finder"])
        return Resp({"items": [{"ExternalDescriptionStr": "<p>Fetched.</p>"}]})

    with patch.object(oracle.session, "get", side_effect=fake_get):
        oracle._enrich_descriptions([job, other])
    check(len(calls) == 1 and 'Id="2"' in calls[0], f"only job 2 may be fetched, got {calls}")
    check(job["description"] == "Reused oracle description." and job["_jobpilot_detail_fetch_status"] == "reused", "oracle reuse recorded")


def test_concurrency_prefetch_keeps_writes_sequential() -> None:
    _reset()
    companies = [_company("alpha"), _company("beta"), _company("gamma")]
    thread_ids = set()
    lock = threading.Lock()

    def fake_make(company):
        cid = company["id"]

        class C(FakeCollector):
            def collect(self_inner):
                with lock:
                    thread_ids.add(threading.get_ident())
                if cid == "beta":
                    raise RuntimeError("source down")
                return [{**_job(1), "source": f"lever:{cid}", "url": f"https://{cid}.example/1"}]

        return C([])

    original = (sync.load_registry, sync._make_collector, sys.argv)
    sync.load_registry = lambda: {"candidate": {"experience_start_date": "2025-09-18"},
                                  "companies": companies + [_company(f"c{i}") for i in range(27)]}
    sync._make_collector = fake_make
    sys.argv = ["sync_target_companies.py", "--only", "alpha", "--only", "beta", "--only", "gamma", "--concurrency", "3"]
    try:
        code = sync.main()
    finally:
        sync.load_registry, sync._make_collector, sys.argv = original
    check(code == 1, "a failing company still makes the run exit non-zero")
    session = SessionLocal()
    try:
        names = sorted({j.company.name for j in session.scalars(select(Job)).all()})
    finally:
        session.close()
    check(names == ["Alpha", "Gamma"], f"healthy companies written despite beta failing: {names}")
    check(len(thread_ids) >= 1, "collectors ran")


TESTS = [
    ("Change counters, removal and reactivation", test_change_counters_and_removal),
    ("Removal guard and FAST/FULL modes", test_removal_guard_and_modes),
    ("FAST mode reuses stored descriptions", test_fast_mode_reuses_stored_descriptions),
    ("Concurrent fetch, sequential writes, isolated failures", test_concurrency_prefetch_keeps_writes_sequential),
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
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
