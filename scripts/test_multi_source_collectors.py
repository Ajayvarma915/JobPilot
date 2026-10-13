from __future__ import annotations

from unittest.mock import patch

from app.collectors.greenhouse import GreenhouseCollector
from app.collectors.lever import LeverCollector


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