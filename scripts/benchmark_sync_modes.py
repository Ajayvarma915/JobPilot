"""Compare FULL and FAST sync on a mocked Workday source (no network, no database).

Run:  python -m scripts.benchmark_sync_modes
Shows how many detail requests each mode makes on a second sync of 200 known jobs where
10 postings changed and 5 are new, and which of those changes each mode actually sees.
"""
from __future__ import annotations

from app.collectors.workday import WorkdayCollector

KNOWN = 200
CHANGED = 10
NEW = 5


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _run(mode: str):
    collector = WorkdayCollector(tenant="t", site="s", company_name="T", host="https://t.wd5.myworkdayjobs.com",
                                 page_size=100, max_pages=5, fetch_details=True)
    ids = [f"R{i}" for i in range(KNOWN + NEW)]
    postings = [{"title": "Software Engineer", "externalPath": f"/job/IN/x_{i}", "jobReqId": i, "locationsText": "India"} for i in ids]
    pages = [_Response({"total": len(ids), "jobPostings": postings[:100]}),
             _Response({"total": 0, "jobPostings": postings[100:200]}),
             _Response({"total": 0, "jobPostings": postings[200:]})]
    collector.session.post = lambda *a, **k: pages.pop(0)
    requests = {"detail": 0}

    def fake_detail(path):
        requests["detail"] += 1
        edited = path.split("_")[-1] in {f"R{i}" for i in range(CHANGED)}
        return {"description": "NEW text" if edited else "same text", "_jobpilot_detail_fetch_status": "fetched"}

    collector._fetch_detail = fake_detail
    if mode == "fast":
        collector.known_descriptions = {f"R{i}": "same text" for i in range(KNOWN)}
    jobs = collector.collect()
    seen_edits = sum(1 for j in jobs if j["description"] == "NEW text")
    seen_new = sum(1 for j in jobs if int(j["external_id"][1:]) >= KNOWN)
    return requests["detail"], seen_edits, seen_new


def main() -> int:
    print(f"Second sync: {KNOWN} known jobs, {CHANGED} with edited descriptions, {NEW} new.\n")
    print(f"{'mode':6} {'detail requests':>16} {'edited seen':>12} {'new seen':>9}")
    for mode in ("full", "fast"):
        details, edited, new = _run(mode)
        print(f"{mode:6} {details:16} {f'{edited}/{CHANGED}':>12} {f'{new}/{NEW}':>9}")
    print("\nTrade-off: FAST makes far fewer requests and still finds every new posting, but it does not see edits")
    print("to descriptions of jobs it already stored. Use FULL to pick those up and to detect removed jobs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
