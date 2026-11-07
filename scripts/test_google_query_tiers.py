from unittest.mock import patch

from scripts import sync_target_companies as sync_module
from scripts.sync_target_companies import google_query_plan


def run_tests():
    configured = [
        "Software Engineer", "Software Development Engineer", "Backend Engineer",
        "Full Stack Engineer", "Frontend Engineer", "Data Engineer",
        "Machine Learning Engineer", "AI Engineer", "DevOps Engineer",
        "Site Reliability Engineer", "Platform Engineer", "Security Software Engineer",
    ]
    full = google_query_plan(configured, fast_scan=False)
    fast = google_query_plan(configured, fast_scan=True)
    expected_fallback = {"Frontend Engineer", "DevOps Engineer", "Platform Engineer"}
    assert full == configured, "Full mode must preserve the complete configured search plan"
    assert len(fast) == 9, f"Expected 9 primary queries; got {len(fast)}"
    assert not (set(fast) & expected_fallback), "Fast mode must omit only the observed low-yield queries"
    assert set(configured) - set(fast) == expected_fallback, "No other query may be omitted"
    assert google_query_plan(configured, fast_scan=True) == fast, "Query plan must be deterministic"
    assert google_query_plan([" frontend engineer ", "Software Engineer"], fast_scan=True) == ["Software Engineer"]
    print("PASS - full mode preserves all 12 Google search batches")
    print("PASS - fast mode omits only the three observed low-yield batches")
    print("PASS - primary query coverage remains intact")
    print("PASS - matching is case/whitespace tolerant and deterministic")

    # Exercise the real sync_company handoff without making network or DB calls.
    company = {
        "id": "google",
        "name": "Google",
        "integration": {
            "provider": "google_careers",
            "status": "configured_needs_live_validation",
            "verified": False,
            "settings": {"queries": configured, "location": "India"},
        },
    }
    captured = []

    class EmptyCollector:
        def collect(self):
            return []

    def collector_factory(company_arg):
        captured.append(company_arg)
        return EmptyCollector()

    with patch.object(sync_module, "_make_collector", side_effect=collector_factory):
        sync_module.sync_company(
            company, dry_run=True, maximum_required_years=2,
            allow_unverified=True, fast_google_scan=True,
        )
    assert len(captured[-1]["integration"]["settings"]["queries"]) == 9
    assert len(company["integration"]["settings"]["queries"]) == 12, "Fast mode must not mutate the registry payload"
    with patch.object(sync_module, "_make_collector", side_effect=collector_factory):
        sync_module.sync_company(
            company, dry_run=True, maximum_required_years=2,
            allow_unverified=True, fast_google_scan=False,
        )
    assert len(captured[-1]["integration"]["settings"]["queries"]) == 12
    print("PASS - fast mode passes the reduced plan without mutating registry settings")
    print("PASS - full mode passes all 12 queries to the collector")


if __name__ == "__main__":
    run_tests()
