from __future__ import annotations

from app.collectors.amazon_jobs import AmazonJobsCollector


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def main() -> int:
    payload = [
        {
            "id": "100",
            "title": "Software Development Engineer II",
            "job_path": "/en/jobs/100",
            "location": "IN, KA, Bengaluru",
            "description": "Full job description with qualifications already supplied by search API.",
        },
        {
            "id": "200",
            "title": "Software Development Engineer",
            "job_path": "/en/jobs/200",
            "location": "IN, TS, Hyderabad",
        },
    ]

    collector = AmazonJobsCollector(
        max_pages_per_band=1,
        page_size=2,
        experience_bands=("one_to_three_years",),
        fetch_details=True,
        max_detail_fetch=10,
    )
    collector.session.get = lambda *args, **kwargs: FakeResponse(payload)

    requested_details = []
    def fake_detail(url):
        requested_details.append(url)
        return {"description": "Detail description fetched because search description was missing."}

    collector._fetch_detail = fake_detail
    jobs = collector.collect()

    assert len(jobs) == 2
    assert requested_details == ["https://www.amazon.jobs/en/jobs/200"]
    assert "already supplied" in jobs[0]["description"]
    assert "Detail description fetched" in jobs[1]["description"]

    print("PASS - Amazon does not refetch descriptions already supplied by search JSON")
    print("PASS - Amazon detail fallback still runs for missing descriptions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
