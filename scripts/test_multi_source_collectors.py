from __future__ import annotations

from unittest.mock import patch

from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector
from app.collectors.workday import WorkdayCollector


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_greenhouse_normalization() -> None:
    payload = {
        "jobs": [
            {
                "id": 12345,
                "title": "Software Engineer",
                "absolute_url": (
                    "https://boards.greenhouse.io/example/jobs/12345"
                ),
                "location": {"name": "Bengaluru, India"},
                "offices": [
                    {
                        "name": "Hyderabad Office",
                        "location": "Hyderabad, India",
                    }
                ],
                "content": (
                    "&lt;p&gt;Build APIs.&lt;/p&gt;"
                    "&lt;ul&gt;&lt;li&gt;Write tests.&lt;/li&gt;&lt;/ul&gt;"
                ),
            },
            {
                "id": 12345,
                "title": "Duplicate result",
                "absolute_url": (
                    "https://boards.greenhouse.io/example/jobs/12345"
                ),
                "location": {"name": "Bengaluru, India"},
                "content": "Duplicate.",
            },
        ]
    }

    collector = GreenhouseCollector(
        board_token="example",
        company_name="Example Inc",
        website="https://example.com",
        careers_url="https://example.com/careers",
    )

    with patch.object(
        collector.session,
        "get",
        return_value=FakeResponse(payload),
    ):
        jobs = collector.collect()

    check(len(jobs) == 1, "Greenhouse duplicate jobs were not removed.")

    job = jobs[0]

    check(
        job["external_id"] == "12345",
        "Greenhouse ID was not normalized.",
    )
    check(
        job["company"] == "Example Inc",
        "Greenhouse company mismatch.",
    )
    check(
        job["source"] == "greenhouse:example",
        "Board-specific source is missing.",
    )
    check(
        job["location"] == [
            "Bengaluru, India",
            "Hyderabad, India",
        ],
        "Greenhouse office locations were not retained.",
    )
    check(
        "Build APIs." in job["description"],
        "Greenhouse HTML content was not parsed.",
    )
    check(
        "Write tests." in job["description"],
        "Greenhouse list content was not parsed.",
    )


def test_lever_normalization() -> None:
    payload = [
        {
            "id": "posting-123",
            "text": "Backend Engineer",
            "hostedUrl": (
                "https://jobs.lever.co/example/posting-123"
            ),
            "applyUrl": (
                "https://jobs.lever.co/example/posting-123/apply"
            ),
            "categories": {
                "location": "Hyderabad, India",
                "commitment": "Full-time",
                "team": "Engineering",
            },
            "workplaceType": "onsite",
            "description": (
                "&lt;p&gt;Build reliable services.&lt;/p&gt;"
            ),
            "lists": [
                {
                    "text": "Requirements",
                    "content": (
                        "&lt;ul&gt;&lt;li&gt;Know Python.&lt;/li&gt;&lt;/ul&gt;"
                    ),
                }
            ],
        },
        {
            "id": "posting-123",
            "text": "Duplicate",
            "hostedUrl": (
                "https://jobs.lever.co/example/posting-123"
            ),
        },
    ]

    collector = LeverCollector(
        site="example",
        company_name="Example Inc",
    )

    with patch.object(
        collector.session,
        "get",
        return_value=FakeResponse(payload),
    ):
        jobs = collector.collect()

    check(len(jobs) == 1, "Lever duplicate jobs were not removed.")

    job = jobs[0]

    check(
        job["external_id"] == "posting-123",
        "Lever ID was not normalized.",
    )
    check(
        job["company"] == "Example Inc",
        "Lever company mismatch.",
    )
    check(
        job["source"] == "lever:global:example",
        "Site-specific source is missing.",
    )
    check(
        job["location"] == ["Hyderabad, India"],
        "Lever location is missing.",
    )
    check(
        job["employment_type"] == "Full-time",
        "Lever commitment was not mapped.",
    )
    check(
        "Build reliable services." in job["description"],
        "Lever description is missing.",
    )
    check(
        "Know Python." in job["description"],
        "Lever list content is missing.",
    )


def test_workday_filter_and_page_limit() -> None:
    """Regression: NVIDIA's board is far larger than the page limit, so collection stopped at 500 silently."""

    def collector_for(**kwargs: object) -> tuple[WorkdayCollector, list[dict]]:
        collector = WorkdayCollector("example", "Careers", "Example Inc", host="example.wd1.myworkdayjobs.com",
                                     page_size=2, fetch_details=False, **kwargs)
        sent: list[dict] = []

        def post(url: str, json: dict, timeout: int) -> FakeResponse:
            sent.append(json)
            offset = json["offset"]
            return FakeResponse({"total": 5 if offset == 0 else 0, "jobPostings": [
                {"title": f"Software Engineer {n}", "externalPath": f"/job/{n}", "locationsText": "Bengaluru, India"}
                for n in range(offset, min(offset + 2, 5))]})

        collector.session.post = post  # type: ignore[method-assign]
        return collector, sent

    facets = {"locationHierarchy1": ["india-id"]}
    complete, sent = collector_for(max_pages=3, applied_facets=facets)
    jobs = complete.collect()
    check(len(jobs) == 5 and jobs.partial_note is None, f"all five read: {len(jobs)}, {jobs.partial_note}")
    check(all(body["appliedFacets"] == facets for body in sent), "the site's filter is sent with every page")

    capped, _ = collector_for(max_pages=2)
    jobs = capped.collect()
    check(len(jobs) == 4 and "4 of 5" in str(jobs.partial_note), f"hitting the limit is reported: {jobs.partial_note}")


def main() -> int:
    tests = [
        (
            "Greenhouse mapping, multi-location, HTML and deduplication",
            test_greenhouse_normalization,
        ),
        (
            "Lever mapping, description, metadata and deduplication",
            test_lever_normalization,
        ),
        (
            "Workday sends the site filter and reports a cut-off collection",
            test_workday_filter_and_page_limit,
        ),
    ]

    print("=" * 72)
    print("JobPilot Multi-Source Collector Tests")
    print("=" * 72)

    passed = 0
    failed = 0

    for index, (name, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {index}: PASS - {name}")
        except Exception as exc:
            failed += 1
            print(
                f"Test {index}: FAIL - {name}\n"
                f"  {type(exc).__name__}: {exc}"
            )

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: Multi-source collector tests failed.")
        return 1

    print("SUCCESS: Multi-source collector tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())