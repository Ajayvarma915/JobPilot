from __future__ import annotations

import threading
import time

from scripts.sync_target_companies import _CompositeCollector


class FakeSearchCollector:
    lock = threading.Lock()
    active = 0
    peak = 0

    def __init__(self, index: int):
        self.index = index

    def collect(self):
        with type(self).lock:
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
        time.sleep(0.04)
        with type(self).lock:
            type(self).active -= 1
        return [{
            "external_id": str(self.index),
            "url": f"https://jobs/{self.index}",
            "title": f"Software Engineer {self.index}",
        }]


def main() -> int:
    FakeSearchCollector.active = 0
    FakeSearchCollector.peak = 0
    collectors = [FakeSearchCollector(i) for i in range(8)]
    results = _CompositeCollector(
        collectors,
        fetch_details=False,
        search_workers=3,
    ).collect()

    assert [job["external_id"] for job in results] == [str(i) for i in range(8)]
    assert 2 <= FakeSearchCollector.peak <= 3, FakeSearchCollector.peak

    capped = _CompositeCollector([], fetch_details=False, search_workers=99)
    assert capped.search_workers == 4

    print("PASS - Google query batches execute concurrently")
    print(f"PASS - search concurrency stayed within cap (peak={FakeSearchCollector.peak})")
    print("PASS - configured search concurrency is hard-capped at 4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
