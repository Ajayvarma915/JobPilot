from __future__ import annotations

import threading
import time

import app.collectors.google_careers as google_module
from app.collectors.google_careers import GoogleCareersCollector


class FakeDetailFetcher:
    lock = threading.Lock()
    active = 0
    peak = 0

    def fetch(self, url, fallback_title=None):
        with self.lock:
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
        time.sleep(0.03)
        with self.lock:
            type(self).active -= 1
        return {
            "title": fallback_title,
            "description": "Full description",
            "sections": {"minimum qualifications": "2 years"},
        }


def main() -> int:
    google_module.GoogleJobDetailFetcher = FakeDetailFetcher
    collector = GoogleCareersCollector(
        fetch_details=False,
        detail_workers=3,
    )
    jobs = [
        {"external_id": str(i), "url": f"https://jobs/{i}", "title": f"Job {i}"}
        for i in range(9)
    ]
    enriched = collector.enrich_jobs(jobs)

    assert len(enriched) == 9
    assert all(job.get("description") == "Full description" for job in enriched)
    assert 2 <= FakeDetailFetcher.peak <= 3, FakeDetailFetcher.peak

    print("PASS - Google detail pages are fetched concurrently")
    print(f"PASS - concurrency stayed within the configured cap (peak={FakeDetailFetcher.peak})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
