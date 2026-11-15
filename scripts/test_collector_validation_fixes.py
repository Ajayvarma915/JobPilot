"""Regression tests for collector bugs found by live dry-run validation (14 Nov).

These use mocked responses, so they only prove the code behaves as designed.
The behaviours themselves were checked against the real endpoints:
  * Uber Oracle feed ignores the country parameter -> filter client-side.
  * Amazon ignores `country[]`; `normalized_country_code[]` is the working one.
"""
from __future__ import annotations

from unittest.mock import patch

from app.collectors.amazon_jobs import AmazonJobsCollector
from app.collectors.oracle_hcm import OracleHCMCollector


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self.payload


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _oracle_rows() -> dict:
    return {"items": [{"requisitionList": [
        {"Id": "1", "Title": "Software Engineer", "PrimaryLocation": "Bengaluru, India", "PrimaryLocationCountry": "IN"},
        {"Id": "2", "Title": "Software Engineer", "PrimaryLocation": "San Francisco, CA, United States", "PrimaryLocationCountry": "US"},
        {"Id": "3", "Title": "Backend Engineer", "PrimaryLocation": "Hyderabad, India"},  # no country field
    ]}]}


def test_oracle_country_filter_is_applied_client_side() -> None:
    collector = OracleHCMCollector(base_url="https://t.fa.ocs.oraclecloud.com", site_number="UberCareers",
                                   company_name="Uber", country_code="IN", page_size=100)
    with patch.object(collector.session, "get", return_value=FakeResponse(_oracle_rows())):
        jobs = collector.collect()
    ids = [job["external_id"] for job in jobs]
    check(ids == ["1", "3"], f"US row must be dropped, India and country-less rows kept; got {ids}")


def test_oracle_detail_fetch_is_bounded_and_fault_tolerant() -> None:
    rows = {"items": [{"requisitionList": [
        {"Id": "1", "Title": "Software Engineer", "PrimaryLocationCountry": "IN", "ShortDescriptionStr": "Already described."},
        {"Id": "2", "Title": "Backend Engineer", "PrimaryLocationCountry": "IN"},
        {"Id": "3", "Title": "Data Engineer", "PrimaryLocationCountry": "IN"},
        {"Id": "4", "Title": "Platform Engineer", "PrimaryLocationCountry": "IN"},
    ]}]}
    detail_ok = FakeResponse({"items": [{"ExternalDescriptionStr": "<p>Build services.</p>",
                                          "ExternalQualificationsStr": "<p>1 year of experience.</p>"}]})
    detail_empty = FakeResponse({"items": [{}]})
    calls: list[str] = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        if url.endswith("recruitingCEJobRequisitions"):
            return FakeResponse(rows)
        finder = params["finder"]
        if 'Id="2"' in finder:
            return detail_ok
        if 'Id="3"' in finder:
            raise RuntimeError("network down")
        return detail_empty

    collector = OracleHCMCollector(base_url="https://t.fa.ocs.oraclecloud.com", site_number="UberCareers",
                                   company_name="Uber", fetch_details=True, max_detail_fetch=3)
    with patch.object(collector.session, "get", side_effect=fake_get):
        jobs = {job["external_id"]: job for job in collector.collect()}

    detail_calls = [c for c in calls if c.endswith("recruitingCEJobRequisitionDetails")]
    check(len(detail_calls) == 3, f"Detail only for jobs without a description (ids 2,3,4); got {len(detail_calls)}")
    check(jobs["1"]["_jobpilot_detail_fetch_status"] == "not_needed", "Described job must not trigger a detail request")
    check(jobs["2"]["_jobpilot_detail_fetch_status"] == "fetched" and "1 year of experience" in jobs["2"]["description"],
          "Description and qualifications must be merged into the job")
    check(jobs["3"]["_jobpilot_detail_fetch_status"] == "failed" and not jobs["3"].get("description"),
          "A failed detail request must not fail the whole source")
    check(jobs["4"]["_jobpilot_detail_fetch_status"] == "fetched_without_description", "Empty detail reported honestly")

    # Cap respected.
    capped = OracleHCMCollector(base_url="https://t.fa.ocs.oraclecloud.com", site_number="UberCareers",
                                company_name="Uber", fetch_details=True, max_detail_fetch=1)
    with patch.object(capped.session, "get", side_effect=fake_get):
        statuses = [job["_jobpilot_detail_fetch_status"] for job in capped.collect()]
    check(statuses.count("not_requested") == 2, f"Detail cap must leave extra jobs as not_requested; got {statuses}")


def test_amazon_uses_working_country_filter_and_no_band_by_default() -> None:
    payload = {"jobs": [{"id": "1", "title": "Software Development Engineer", "job_path": "/en/jobs/1",
                         "location": "Hyderabad, India", "description": "Basic qualifications: 1 year."}]}
    collector = AmazonJobsCollector(max_pages_per_band=1, page_size=100, fetch_details=False)
    with patch.object(collector.session, "get", return_value=FakeResponse(payload)) as get_mock:
        collector.collect()
    check(get_mock.call_count == 1, "Without bands there must be exactly one pass, not one per band")
    params = get_mock.call_args.kwargs["params"]
    check(params["normalized_country_code[]"] == "IND", "India filter must use normalized_country_code[]")
    check("country[]" not in params, "Ignored country[] must not be sent")
    check(not any("industry_experience" in key for key in params), "No experience-band filter by default")


def test_amazon_band_filter_still_available_when_requested() -> None:
    payload = {"jobs": [{"id": "1", "title": "SDE", "job_path": "/en/jobs/1", "location": "India", "description": "x"}]}
    collector = AmazonJobsCollector(max_pages_per_band=1, page_size=100, fetch_details=False,
                                    experience_bands=("one_to_three_years",))
    with patch.object(collector.session, "get", return_value=FakeResponse(payload)) as get_mock:
        collector.collect()
    check(get_mock.call_args.kwargs["params"].get("industry_experience[]") == "one_to_three_years",
          "An explicitly requested band must use the array parameter that the server honours")


def test_workday_paginates_past_two_pages_when_total_only_on_first_page() -> None:
    """Live Workday returns `total` on the first page only (Adobe: 246, 0, 0, ...)."""
    from app.collectors.workday import WorkdayCollector

    def page(start: int, count: int, total: int) -> FakeResponse:
        return FakeResponse({"total": total, "jobPostings": [
            {"title": f"Software Engineer {n}", "externalPath": f"/job/IN/Software-Engineer-{n}_R{n}",
             "jobReqId": f"R{n}", "locationsText": "India, Bengaluru"} for n in range(start, start + count)]})

    collector = WorkdayCollector(tenant="t", site="s", company_name="T", host="https://t.wd5.myworkdayjobs.com",
                                 page_size=20, max_pages=25, fetch_details=False)
    pages = [page(0, 20, 50), page(20, 20, 0), page(40, 10, 0)]
    with patch.object(collector.session, "post", side_effect=pages) as post:
        jobs = collector.collect()
    check(len(jobs) == 50, f"All 50 jobs must be collected across three pages, got {len(jobs)}")
    check(post.call_count == 3, f"Expected 3 page requests, got {post.call_count}")

    # When the pages exactly fill the reported total, no extra empty page is requested.
    exact = WorkdayCollector(tenant="t", site="s", company_name="T", host="https://t.wd5.myworkdayjobs.com",
                             page_size=20, max_pages=25, fetch_details=False)
    with patch.object(exact.session, "post", side_effect=[page(0, 20, 40), page(20, 20, 0), page(40, 20, 0)]) as post2:
        jobs2 = exact.collect()
    check(len(jobs2) == 40 and post2.call_count == 2, f"Must stop at the first-page total; got {len(jobs2)} jobs / {post2.call_count} calls")


def test_atlassian_listing_normalization() -> None:
    """Shape copied from the live feed (https://www.atlassian.com/endpoint/careers/listings)."""
    from app.collectors.atlassian_careers import AtlassianCareersCollector

    row = {
        "id": 27589, "portalId": 242, "title": "Data Platform Engineer", "type": "Full-Time", "category": "Engineering",
        "locations": ["Bengaluru - India -   Bengaluru,  560071 India", "Remote - Remote", "Remote - Remote"],
        "overview": "<p><strong>Working at Atlassian</strong></p><p>Long boilerplate.</p>",
        "responsibilities": "<ul><li><p>Build the data platform.</p></li></ul>",
        "qualifications": "<ul><li><p>1+ years in software engineering.</p></li></ul>",
        "applyUrl": "https://careers-apac-atlassian.icims.com/jobs/27589/data-platform-engineer/job?mode=apply",
        "portalJobPost": {"portalUrl": "https://careers-apac-atlassian.icims.com/jobs/27589/data-platform-engineer/job",
                          "updatedDate": "2026-10-29 12:41 PM"},
    }
    duplicate = dict(row)  # the live feed repeats ids
    no_title = {"id": 5, "title": "", "applyUrl": "https://x"}
    collector = AtlassianCareersCollector()
    with patch.object(collector.session, "get", return_value=FakeResponse([row, duplicate, no_title, "junk"])) as get:
        jobs = collector.collect()
    check(get.call_count == 1, "Atlassian needs exactly one request, no per-job detail requests")
    check(len(jobs) == 1, f"Duplicate ids and unusable rows must be dropped, got {len(jobs)}")
    job = jobs[0]
    check(job["external_id"] == "27589" and job["source"] == "atlassian_careers", "id/source")
    check(job["url"].endswith("/job") and "mode=apply" not in job["url"], "Use the job page URL, not the apply-mode URL")
    check(job["location"] == ["Bengaluru - India - Bengaluru, 560071 India", "Remote - Remote"], f"locations cleaned: {job['location']}")
    check(job["description"].startswith("Qualifications:") and "1+ years" in job["description"], "Qualifications must come first")
    check(job["posted_at"] is None, "Do not invent a posting date from the updated timestamp")
    from app.services.target_role_policy import is_india_or_remote_eligible
    check(is_india_or_remote_eligible(job)[0], "Bengaluru entry must make the job India-eligible")


TESTS = [
    ("Atlassian feed normalization", test_atlassian_listing_normalization),
    ("Workday paginates beyond two pages", test_workday_paginates_past_two_pages_when_total_only_on_first_page),
    ("Oracle country filter applied client-side", test_oracle_country_filter_is_applied_client_side),
    ("Oracle detail fetch bounded and fault tolerant", test_oracle_detail_fetch_is_bounded_and_fault_tolerant),
    ("Amazon default search uses working country filter", test_amazon_uses_working_country_filter_and_no_band_by_default),
    ("Amazon band filter optional", test_amazon_band_filter_still_available_when_requested),
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
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
