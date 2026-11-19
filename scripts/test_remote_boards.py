"""Tests for the remote job board collectors and sync (fake feeds, temp database, no network)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_remote_boards.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.collectors.remote_boards import (  # noqa: E402
    HimalayasCollector, RemoteOkCollector, RemotiveCollector, WeWorkRemotelyCollector,
)
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.models import Job  # noqa: E402
from scripts.sync_remote_boards import sync_board  # noqa: E402

GOOD = "Minimum qualifications: 1 year of software development experience. Build services in Python."
VAGUE = "Build things with a friendly team every single day."
SOURCE = "remote_board:remotive"


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeResponse:
    def __init__(self, payload=None, content=b""):
        self.payload, self.content = payload, content

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def test_collectors_normalise_each_board() -> None:
    remotive = RemotiveCollector(session=FakeSession(FakeResponse({"jobs": [
        {"id": 1, "company_name": "Acme", "title": "Junior Backend Engineer", "url": "https://r.example/1",
         "candidate_required_location": "Worldwide", "description": "<p>Hello <b>there</b></p>",
         "publication_date": "2026-11-14T20:33:53", "job_type": "full_time"}]})))
    job = remotive.collect()[0]
    check(job["location"] == ["Remote - Worldwide"] and job["source"] == SOURCE, job)
    check(job["description"] == "Hello there", job["description"])
    check(job["employment_type"] == "Full Time" and job["posted_at"].year == 2026, job)

    remoteok = RemoteOkCollector(session=FakeSession(FakeResponse([
        {"legal": "terms"},
        {"id": "9", "company": "Beta", "position": "Software Engineer", "url": "https://ok.example/9",
         "location": "", "description": "x", "date": "2026-11-17T00:00:29+00:00"}])))
    jobs = remoteok.collect()
    check(len(jobs) == 1 and jobs[0]["company"] == "Beta" and jobs[0]["location"] == ["Remote - Worldwide"],
          "the legal notice row is skipped")

    pages = [
        FakeResponse({"jobs": [{"guid": "g1", "companyName": "Gamma", "title": "Engineer", "applicationLink": "https://h.example/1",
                                "locationRestrictions": ["India", "Nepal"], "description": "d", "pubDate": "1794970778"}],
                      "nextCursor": "c2"}),
        FakeResponse({"jobs": [{"guid": "g2", "companyName": "Delta", "title": "Engineer", "applicationLink": "https://h.example/2",
                                "locationRestrictions": [], "description": "d"}], "nextCursor": None}),
    ]
    session = FakeSession(*pages)
    jobs = HimalayasCollector(session=session).collect()
    check([j["location"] for j in jobs] == [["Remote - India, Nepal"], ["Remote - Worldwide"]], "regions")
    check(len(session.calls) == 2 and session.calls[1][1]["params"]["cursor"] == "c2", "cursor paging uses nextCursor")

    rss = (b"<rss><channel><item><title>Epsilon: Software Engineer</title><region>Anywhere in the World</region>"
           b"<link>https://w.example/1</link><guid>https://w.example/1</guid><description>&lt;p&gt;Role&lt;/p&gt;</description>"
           b"<pubDate>Mon, 17 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>")
    jobs = WeWorkRemotelyCollector(session=FakeSession(FakeResponse(content=rss))).collect()
    check(len(jobs) == 1 and jobs[0]["company"] == "Epsilon" and jobs[0]["title"] == "Software Engineer"
          and jobs[0]["location"] == ["Remote - Worldwide"], jobs)


def job(key, title, region, description=GOOD, company="Acme"):
    return {"external_id": f"remotive-{key}", "company": company, "title": title, "location": [f"Remote - {region}"],
            "workplace_type": "remote", "url": f"https://r.example/{key}", "description": description, "source": SOURCE}


def run(batch):
    return sync_board("remotive", batch, source=SOURCE, dry_run=False, max_years=2.0)


def test_sync_stores_by_eligibility_and_closes_gone_jobs() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    one = job("1", "Junior Software Engineer", "Worldwide")
    two = job("2", "Software Engineer", "Worldwide", description=VAGUE)  # years not stated: held for review
    result = run([one, two,
                  job("3", "Software Engineer", "USA, Canada"),  # foreign only: dropped
                  job("4", "Senior Staff Engineer", "Worldwide")])  # too senior: dropped
    check((result.clean, result.review, result.skipped, result.inserted) == (1, 1, 2, 2), result)

    body = client.get("/api/jobs", params={"review_scope": "remote", "career_level": "all", "limit": 50}).json()
    shown = {item["title"]: item for item in body["items"]}
    check(set(shown) == {"Junior Software Engineer", "Software Engineer"}, f"remote tab shows the two kept jobs: {set(shown)}")
    check(shown["Software Engineer"]["review"]["status"] == "pending" and shown["Junior Software Engineer"]["review"] is None,
          "the unclear job says why; the clean one has no flag")
    main_list = client.get("/api/jobs", params={"career_level": "all", "location": "India"}).json()["items"]
    check(not main_list, "remote jobs stay out of the main list")

    tiny = run([])
    check("closure check skipped" in (tiny.note or "") and tiny.removed == 0, f"a tiny answer closes nothing: {tiny.note}")
    check(run([one, two]).removed == 0, "both still listed, nothing closed")
    gone = run([two, job("5", "Junior Software Engineer", "Worldwide", company="Zed")])
    check(gone.removed == 1, f"job 1 left the board, so it is closed: {gone}")
    session = SessionLocal()
    try:
        check(session.query(Job).filter(Job.is_active.is_(False)).count() == 1, "exactly one job is closed")
    finally:
        session.close()

    restricted = run([job("6", "Software Engineer (Remote @ Colombia)", "Worldwide"), job("7", "Software Engineer (U.S. Based)", "Worldwide"),
                      job("8", "Software Engineer", "Palo Alto"), job("9", "Software Engineer", "India")])
    check(restricted.inserted == 1 and restricted.skip_reasons.get("title_names_a_region_outside_india") == 2
          and restricted.skip_reasons.get("region_not_open_to_india") == 1, f"restrictions are honoured: {restricted}")


TESTS = [
    ("Collectors normalise each board", test_collectors_normalise_each_board),
    ("Sync keeps eligible remote jobs, holds unclear ones, closes gone ones", test_sync_stores_by_eligibility_and_closes_gone_jobs),
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
