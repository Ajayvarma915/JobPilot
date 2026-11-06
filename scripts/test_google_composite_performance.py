from __future__ import annotations

from scripts.sync_target_companies import _CompositeCollector


class FakeGoogleCollector:
    def __init__(self, jobs):
        self.jobs = jobs
        self.enriched_batches = []

    def collect(self):
        return list(self.jobs)

    def enrich_jobs(self, jobs):
        self.enriched_batches.append([job["external_id"] for job in jobs])
        return [dict(job, full_description="loaded-once") for job in jobs]


def main() -> int:
    first = FakeGoogleCollector([
        {"external_id": "1", "url": "https://jobs/1", "title": "Backend Engineer"},
        {"external_id": "2", "url": "https://jobs/2", "title": "Software Engineer"},
    ])
    second = FakeGoogleCollector([
        {"external_id": "1", "url": "https://jobs/1", "title": "Backend Engineer"},
        {"external_id": "3", "url": "https://jobs/3", "title": "Data Engineer"},
    ])

    results = _CompositeCollector(
        [first, second],
        fetch_details=True,
    ).collect()

    assert [job["external_id"] for job in results] == ["1", "2", "3"]
    assert first.enriched_batches == [["1", "2", "3"]]
    assert second.enriched_batches == []
    assert all(job.get("full_description") == "loaded-once" for job in results)

    no_detail = _CompositeCollector(
        [
            FakeGoogleCollector([{"external_id": "4", "url": "https://jobs/4"}]),
        ],
        fetch_details=False,
    ).collect()
    assert len(no_detail) == 1
    print("PASS - cross-query duplicates are removed before one enrichment pass")
    print("PASS - disabling detail fetching keeps the collector cards-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
