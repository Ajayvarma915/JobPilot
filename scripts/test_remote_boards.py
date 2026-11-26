"""Tests for the remote job board collectors and sync (fake feeds, temp database, no network)."""
from __future__ import annotations

from datetime import datetime, timedelta
import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_remote_boards.db")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

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
    jobs = HimalayasCollector(session=session, searches=()).collect()
    check([j["location"] for j in jobs] == [["Remote - India, Nepal"], ["Remote - Worldwide"]], "regions")
    check(len(session.calls) == 2 and session.calls[1][1]["params"]["cursor"] == "c2", "cursor paging uses nextCursor")

    rss = (b"<rss><channel><item><title>Epsilon: Software Engineer</title><region>Anywhere in the World</region>"
           b"<link>https://w.example/1</link><guid>https://w.example/1</guid><description>&lt;p&gt;Role&lt;/p&gt;</description>"
           b"<pubDate>Mon, 17 Nov 2026 10:00:00 +0000</pubDate></item></channel></rss>")
    jobs = WeWorkRemotelyCollector(session=FakeSession(FakeResponse(content=rss))).collect()
    check(len(jobs) == 1 and jobs[0]["company"] == "Epsilon" and jobs[0]["title"] == "Software Engineer"
          and jobs[0]["location"] == ["Remote - Worldwide"], jobs)


class UrlSession(FakeSession):
    """Answers by URL text, so collectors that call several pages can be tested."""

    def __init__(self, routes):
        super().__init__(FakeResponse(payload={}))
        self.routes = routes

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for marker, response in self.routes:
            if marker in url:
                return response
        raise AssertionError(f"unexpected request {url}")


class TextResponse(FakeResponse):
    def __init__(self, text, status=200):
        super().__init__()
        self.text, self.status_code = text, status


def yc_html(props):
    import html as html_lib
    import json as json_lib

    return TextResponse('<html><div id="app" data-page="' + html_lib.escape(json_lib.dumps({"props": props}), quote=True) + '"></div></html>')


def test_new_boards_normalise() -> None:
    from app.collectors.remote_boards import JobicyCollector, WorkingNomadsCollector, YCombinatorCollector

    posts = [
        {"id": 1, "title": "Software Engineer", "url": "/companies/acme/jobs/a", "location": "Remote (Worldwide)", "minExperience": "1+ years",
         "companyName": "Acme", "type": "Full-time"},
        {"id": 2, "title": "Software Engineer", "url": "/companies/beta/jobs/b", "location": "HQ / Bengaluru, KA, IN", "minExperience": "Any (new grads ok)",
         "companyName": "Beta", "type": "Full-time"},
        {"id": 3, "title": "Senior Software Engineer", "url": "/companies/gamma/jobs/c", "location": "Remote (US)", "minExperience": "6+ years", "companyName": "Gamma"},
        {"id": 4, "title": "Software Engineer", "url": "/companies/delta/jobs/d", "location": "San Francisco, CA, US", "minExperience": "2+ years", "companyName": "Delta"},
    ]
    session = UrlSession([
        ("/jobs/role/", yc_html({"jobPostings": posts})),
        ("/jobs/location/", yc_html({"jobPostings": []})),
        ("/companies/acme/jobs/a", yc_html({"job": {"description": "**Build** backend services in Python."}})),
        ("/companies/beta/jobs/b", yc_html({"job": {"description": "Join the Bengaluru team."}})),
    ])
    collector = YCombinatorCollector(session=session, pages_per_role=1, pause=0)
    collector.ROLES = ("software-engineer",)
    collector.LOCATIONS = ()
    jobs = {job["company"]: job for job in collector.collect()}
    check(set(jobs) == {"Acme", "Beta", "Gamma", "Delta"}, set(jobs))
    check(jobs["Acme"]["location"] == ["Remote - Worldwide"] and jobs["Acme"]["workplace_type"] == "remote", jobs["Acme"])
    check(jobs["Acme"]["description"].startswith("Minimum qualifications: 1+ years") and "backend services" in jobs["Acme"]["description"], jobs["Acme"]["description"])
    check(jobs["Beta"]["location"] == ["Bengaluru, KA, IN"] and jobs["Beta"]["workplace_type"] == "onsite", jobs["Beta"])
    check("0 years of experience" in jobs["Beta"]["description"], "new grads ok is read as a stated 0 years")
    detail_calls = [url for url, _ in session.calls if "/companies/" in url]
    check(len(detail_calls) == 2, f"descriptions are fetched only for jobs that pass the pre-check: {detail_calls}")
    check(jobs["Gamma"]["location"] == ["Remote - US"] and jobs["Delta"]["workplace_type"] == "onsite", "other jobs keep their place and are not fetched")
    only_list = YCombinatorCollector(session=UrlSession([("/jobs/", yc_html({"jobPostings": posts}))]), pages_per_role=1, pause=0, fetch_details=False)
    only_list.ROLES, only_list.LOCATIONS = ("software-engineer",), ()
    check(len(only_list.collect()) == 4 and not any("/companies/" in url for url, _ in only_list.session.calls), "the still-open check reads lists only")

    jobicy = JobicyCollector(session=FakeSession(FakeResponse({"jobs": [
        {"id": 7, "url": "https://jobicy.com/jobs/7", "jobTitle": "Backend Engineer", "companyName": "Zed", "jobGeo": "Anywhere", "jobType": ["Full-Time"],
         "jobDescription": "<p>Python</p>", "pubDate": "2026-11-18 10:00:00"}]})))
    job = jobicy.collect()[0]
    check((job["external_id"], job["location"], job["source"]) == ("jobicy-7", ["Remote - Worldwide"], "remote_board:jobicy"), job)
    nomads = WorkingNomadsCollector(session=FakeSession(FakeResponse([
        {"url": "https://www.workingnomads.com/job/go/2034803/", "title": "Backend Developer", "company_name": "Nom", "category_name": "Development",
         "location": "Anywhere", "description": "<p>Go</p>", "pub_date": "2026-11-19T07:13:33-05:00"},
        {"url": "https://www.workingnomads.com/job/go/1/", "title": "Content Writer", "company_name": "X", "category_name": "Marketing", "location": "Anywhere"}])))
    found = nomads.collect()
    check(len(found) == 1 and found[0]["external_id"] == "workingnomads-2034803", found)


def test_himalayas_search_adds_india_and_worldwide_results() -> None:
    def listing(guid, restrictions):
        return {"guid": guid, "companyName": "Acme", "title": "Backend Engineer", "applicationLink": f"https://h.example/{guid}",
                "locationRestrictions": restrictions, "description": "d"}

    session = UrlSession([
        ("/jobs/api/search", FakeResponse({"jobs": [listing("s-india", ["India", "Nepal"]), listing("s-world", [])]})),
        ("/jobs/api", FakeResponse({"jobs": [listing("browse-1", [])], "nextCursor": None})),
    ])
    collector = HimalayasCollector(session=session, searches=("backend developer",), search_pages=1, pause=0)
    jobs = collector.collect()
    ids = {job["external_id"] for job in jobs}
    check({"himalayas-browse-1", "himalayas-s-india", "himalayas-s-world"} == ids, ids)
    queries = [kw["params"] for url, kw in session.calls if "/search" in url]
    check(any(p.get("country") == "India" for p in queries), f"roles open to India are asked for: {queries}")
    check(any(p.get("worldwide") == "true" for p in queries), "worldwide roles are asked for too")
    only_feed = HimalayasCollector(session=UrlSession([("/jobs/api", FakeResponse({"jobs": [listing("b", [])], "nextCursor": None}))]),
                                   searches=("x",), fetch_details=False, pause=0)
    check(len(only_feed.collect()) == 1 and not any("/search" in url for url, _ in only_feed.session.calls), "the still-open check skips the searches")


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
    just_missed = run([two, job("5", "Junior Software Engineer", "Worldwide", company="Zed")])
    check(just_missed.removed == 0, f"missing from one recent-postings feed does not close a job seen today: {just_missed}")
    session = SessionLocal()
    try:  # pretend job 1 was last shown 20 days ago
        old = session.query(Job).filter(Job.title == "Junior Software Engineer", Job.external_id.like("%1")).one()
        old.last_seen_at = datetime.utcnow() - timedelta(days=20)
        session.commit()
    finally:
        session.close()
    gone = run([two, job("5", "Junior Software Engineer", "Worldwide", company="Zed")])
    check(gone.removed == 1, f"job 1 has not been shown for over 14 days, so it is closed: {gone}")
    session = SessionLocal()
    try:
        check(session.query(Job).filter(Job.is_active.is_(False)).count() == 1, "exactly one job is closed")
    finally:
        session.close()

    restricted = run([job("6", "Software Engineer (Remote @ Colombia)", "Worldwide"), job("7", "Software Engineer (U.S. Based)", "Worldwide"),
                      job("8", "Software Engineer", "Palo Alto"), job("9", "Software Engineer", "India")])
    check(restricted.inserted == 1 and restricted.skip_reasons.get("title_names_a_region_outside_india") == 2
          and restricted.skip_reasons.get("region_not_open_to_india") == 1, f"restrictions are honoured: {restricted}")


def test_list_pages_never_repeat_or_skip_jobs() -> None:
    """Regression: before scores were cached, page 1 was cut by date and page 2 by score, so on a first load
    146 remote rows held only 109 different jobs."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    skills = ("Python", "Java", "Node.js", "Cobol", "Kafka")
    run([job(str(100 + n), f"Software Engineer {skills[n % 5]} Team {n}", "Worldwide",
             description=f"Minimum qualifications:\n1 year of experience with {skills[n % 5]}." + (" Redis and Docker." if n % 3 == 0 else ""))
         for n in range(30)])
    session = SessionLocal()
    try:
        session.execute(text("DELETE FROM job_match_cache")) if inspect(engine).has_table("job_match_cache") else None
        session.commit()
    finally:
        session.close()
    seen: list[int] = []
    scores: list[float] = []
    for offset in (0, 10, 20):
        body = client.get("/api/jobs", params={"review_scope": "remote", "career_level": "all", "limit": 10, "offset": offset}).json()
        seen += [item["id"] for item in body["items"]]
        scores += [item["match"]["score"] for item in body["items"]]
    check(len(seen) == 30 and len(set(seen)) == 30, f"30 jobs, each exactly once: {len(seen)} rows, {len(set(seen))} unique")
    check(scores == sorted(scores, reverse=True), f"one ranking across all pages: {scores}")


TESTS = [
    ("List pages never repeat or skip jobs", test_list_pages_never_repeat_or_skip_jobs),
    ("Collectors normalise each board", test_collectors_normalise_each_board),
    ("YC, Jobicy and Working Nomads are read correctly", test_new_boards_normalise),
    ("Himalayas search adds India and worldwide results", test_himalayas_search_adds_india_and_worldwide_results),
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
