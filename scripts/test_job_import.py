"""Tests for adding a job by link (fake pages, no network)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_job_import.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, engine  # noqa: E402
from app.services import job_import  # noqa: E402
from app.services.job_import import ImportError_, clean_company, fetch_job  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Response:
    def __init__(self, status=200, text="", payload=None):
        self.status_code, self.text, self.payload = status, text, payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise job_import.requests.HTTPError(str(self.status_code))


def public_dns(monkey: bool = True) -> None:
    job_import.socket.getaddrinfo = lambda host, port: [(2, 1, 6, "", ("93.184.216.34", port))] if host != "localhost" else [(2, 1, 6, "", ("127.0.0.1", port))]


def test_address_checks() -> None:
    public_dns()
    for bad in ("http://example.com/job", "ftp://example.com", "not a url", "https://localhost/job"):
        try:
            fetch_job(bad, get=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch")))
            raise AssertionError(f"{bad} should be refused")
        except ImportError_:
            pass


def test_company_names_are_cleaned() -> None:
    check(clean_company("52 Qualcomm India Private Limited") == "Qualcomm", "legal suffixes, numbers and India are dropped")
    check(clean_company("Acme Inc.") == "Acme" and clean_company("Tata Consultancy Services Limited") == "Tata Consultancy Services", "other suffixes")


def test_workday_page_is_read_from_its_json() -> None:
    public_dns()
    seen = []

    def get(url, **kwargs):
        seen.append(url)
        return Response(payload={"jobPostingInfo": {"title": "Associate Engineer", "jobDescription": "<p>Build <b>chips</b></p>", "location": "Bangalore IND",
                                                    "jobReqId": "3098178", "startDate": "2026-11-12", "timeType": "Full time",
                                                    "externalUrl": "https://qualcomm.wd12.myworkdayjobs.com/External/job/Bangalore-IND/Associate-Engineer_3098178"},
                                    "hiringOrganization": {"name": "52 Qualcomm India Private Limited"}})

    job = fetch_job("https://qualcomm.wd12.myworkdayjobs.com/en-US/External/job/Bangalore-IND/Associate-Engineer_3098178", get=get)
    check(seen == ["https://qualcomm.wd12.myworkdayjobs.com/wday/cxs/qualcomm/External/job/Bangalore-IND/Associate-Engineer_3098178"], seen)
    check((job["title"], job["company"], job["external_id"], job["location"]) == ("Associate Engineer", "Qualcomm", "3098178", ["Bangalore IND"]), job)
    check(job["description"] == "Build chips", job["description"])


def test_json_ld_page_and_unreadable_page() -> None:
    public_dns()
    ld = {"@context": "https://schema.org", "@type": "JobPosting", "title": "Backend Engineer", "description": "<p>Python</p>",
          "hiringOrganization": {"@type": "Organization", "name": "Initech Pvt Ltd"}, "datePosted": "2026-11-10",
          "jobLocation": {"@type": "Place", "address": {"addressLocality": "Pune", "addressCountry": "IN"}}, "identifier": {"value": "R-9"}}
    page = f"<html><script type='application/ld+json'>{json.dumps(ld)}</script></html>"
    job = fetch_job("https://careers.initech.example/jobs/9", get=lambda *a, **k: Response(text=page))
    check((job["title"], job["company"], job["location"], job["external_id"]) == ("Backend Engineer", "Initech", ["Pune, IN"], "R-9"), job)
    try:
        fetch_job("https://careers.initech.example/jobs/9", get=lambda *a, **k: Response(text="<html>nothing here</html>"))
        raise AssertionError("an unreadable page must be refused")
    except ImportError_ as exc:
        check("does not publish" in str(exc), str(exc))
    try:
        fetch_job("https://careers.initech.example/jobs/9", get=lambda *a, **k: Response(status=404))
        raise AssertionError("a 404 must be refused")
    except ImportError_ as exc:
        check("not found" in str(exc), str(exc))


def test_endpoint_stores_the_job_once() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    details = {"title": "Associate Engineer", "company": "Qualcomm", "location": ["Bangalore IND"], "description": "Build chips",
               "external_id": "3098178", "posted_at": None, "employment_type": "Full time", "url": "https://q.example/job/3098178"}
    original = api_main.fetch_job
    api_main.fetch_job = lambda url: dict(details)
    try:
        first = client.post("/api/jobs/import-link", json={"url": "https://q.example/job/3098178"})
        check(first.status_code == 201 and first.json()["created"] is True and first.json()["company"] == "Qualcomm", first.text)
        again = client.post("/api/jobs/import-link", json={"url": "https://q.example/job/3098178"}).json()
        check(again["created"] is False and again["job_id"] == first.json()["job_id"], "importing twice does not duplicate")
        listing = client.get("/api/jobs", params={"career_level": "all", "role_scope": "all", "location": "India", "company": "Qualcomm"}).json()
        check(listing["pagination"]["total"] == 1, f"the imported job shows in the list: {listing['pagination']}")
        api_main.fetch_job = lambda url: (_ for _ in ()).throw(ImportError_("That page was not found."))
        failed = client.post("/api/jobs/import-link", json={"url": "https://q.example/x"})
        check(failed.status_code == 422 and "not found" in failed.json()["detail"], failed.text)
    finally:
        api_main.fetch_job = original


def test_page_import_from_the_extension() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    client = TestClient(api_main.app)
    body = {"url": "https://careers.qualcomm.com/careers/job/3098178", "title": "Associate Engineer",
            "company": "52 Qualcomm India Private Limited", "location": ["Bangalore, KA, IN"], "description": "Build chips",
            "external_id": "3098178", "confidence": "structured"}
    first = client.post("/api/jobs/import-page", json=body)
    check(first.status_code == 201 and first.json()["created"] and first.json()["company"] == "Qualcomm", first.text)
    again = client.post("/api/jobs/import-page", json=body).json()
    check(again["created"] is False and again["job_id"] == first.json()["job_id"], "saving twice does not duplicate")
    # without an id the link decides identity, so the same page is still one job
    no_id = {**body, "external_id": None, "url": "https://careers.example.com/job/9", "title": "Engineer", "company": "Example"}
    a, b = client.post("/api/jobs/import-page", json=no_id).json(), client.post("/api/jobs/import-page", json=no_id).json()
    check(a["job_id"] == b["job_id"] and b["created"] is False, "id derived from the link")
    for bad in ("http://careers.example.com/job/1", "https://localhost/job/1", "https://127.0.0.1/job/1", "ftp://x.example/1"):
        check(client.post("/api/jobs/import-page", json={**body, "url": bad}).status_code == 422, f"{bad} is refused")
    check(client.post("/api/jobs/import-page", json={**body, "title": ""}).status_code == 422, "a missing title is refused")
    listing = client.get("/api/jobs", params={"career_level": "all", "role_scope": "all", "location": "India", "company": "Qualcomm"}).json()
    check(listing["pagination"]["total"] == 1, "the saved job shows in the list")


TESTS = [
    ("Only public https pages are fetched", test_address_checks),
    ("Company names are cleaned", test_company_names_are_cleaned),
    ("A Workday page is read from its own JSON", test_workday_page_is_read_from_its_json),
    ("A JobPosting page is read; unreadable or missing pages are refused", test_json_ld_page_and_unreadable_page),
    ("The endpoint stores the job once", test_endpoint_stores_the_job_once),
    ("A job read by the extension is saved once and unsafe pages are refused", test_page_import_from_the_extension),
]


def main() -> int:
    failed = 0
    real = job_import.socket.getaddrinfo
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    job_import.socket.getaddrinfo = real
    engine.dispose()
    api_main.engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
