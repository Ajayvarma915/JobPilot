from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_job_match_fields_and_ordering(client: TestClient) -> None:
    response = client.get(
        "/api/jobs",
        params={"limit": 100, "career_level": "all"},
    )
    check(response.status_code == 200, f"Job endpoint failed: {response.text}")

    data = response.json()
    jobs = data["items"]
    check(bool(jobs), "Expected jobs in the local JobPilot database.")

    scores: list[float] = []

    for job in jobs:
        match = job.get("match")
        check(
            isinstance(match, dict),
            f"Match metadata missing for {job['title']}",
        )
        check(0 <= match["score"] <= 100, "Match score must be between 0 and 100.")
        check(
            match["recommendation"]
            in {"strong_match", "good_match", "review", "low_match"},
            f"Unexpected recommendation: {match['recommendation']}",
        )
        check(isinstance(match["reasons"], list), "Match reasons must be a list.")
        check(isinstance(match["concerns"], list), "Match concerns must be a list.")
        check(
            set(match["score_breakdown"])
            == {"role", "seniority", "experience", "skills", "education", "location"},
            "Score breakdown does not include the expected components.",
        )
        scores.append(float(match["score"]))

    check(scores == sorted(scores, reverse=True), "Jobs are not sorted by match score.")


def test_default_early_filter_and_all_roles_toggle(
    client: TestClient,
) -> None:
    default_response = client.get(
        "/api/jobs",
        params={
            "q": "software engineer",
            "company": "google",
            "location": "Bengaluru",
            "limit": 100,
        },
    )
    check(default_response.status_code == 200, "Default early-career filter failed.")
    default_data = default_response.json()

    check(
        default_data["filters"]["career_level"] == "early",
        "The API should default to early-career suitable jobs.",
    )

    all_response = client.get(
        "/api/jobs",
        params={
            "q": "software engineer",
            "company": "google",
            "location": "Bengaluru",
            "career_level": "all",
            "limit": 100,
        },
    )
    check(all_response.status_code == 200, "All-role filter failed.")
    all_data = all_response.json()

    check(
        all_data["pagination"]["total"] >= default_data["pagination"]["total"],
        "All-role results should not be fewer than early-career results.",
    )


def test_multicity_listing_matches_either_city(
    client: TestClient,
) -> None:
    common_params = {
        "q": "software engineer",
        "company": "google",
        "career_level": "all",
        "limit": 100,
    }

    hyd_response = client.get(
        "/api/jobs",
        params={**common_params, "location": "Hyderabad"},
    )
    blr_response = client.get(
        "/api/jobs",
        params={**common_params, "location": "Bengaluru"},
    )

    check(hyd_response.status_code == 200, "Hyderabad location search failed.")
    check(blr_response.status_code == 200, "Bengaluru location search failed.")

    hyd_jobs = {item["id"]: item for item in hyd_response.json()["items"]}
    blr_jobs = {item["id"]: item for item in blr_response.json()["items"]}
    shared_ids = set(hyd_jobs).intersection(blr_jobs)

    check(
        bool(shared_ids),
        "Expected at least one job listing that includes both cities.",
    )

    sample_id = next(iter(shared_ids))
    hyd_job = hyd_jobs[sample_id]
    blr_job = blr_jobs[sample_id]

    check(
        hyd_job["location"].lower().startswith("hyderabad"),
        "Hyderabad search should display Hyderabad as the selected location.",
    )
    check(
        blr_job["location"].lower().startswith("bengaluru"),
        "Bengaluru search should display Bengaluru as the selected location.",
    )
    check(
        hyd_job["all_locations"] == blr_job["all_locations"],
        "The original full location list must remain available in both searches.",
    )


def main() -> int:
    tests = [
        ("Structured match fields and score ordering", test_job_match_fields_and_ordering),
        ("Early-career default and all-role toggle", test_default_early_filter_and_all_roles_toggle),
        ("Multi-city jobs match either city", test_multicity_listing_matches_either_city),
    ]

    print("=" * 72)
    print("JobPilot Match API Regression Tests")
    print("=" * 72)

    passed = 0
    failed = 0

    with TestClient(app) as client:
        for index, (name, test) in enumerate(tests, start=1):
            try:
                test(client)
                passed += 1
                print(f"Test {index}: PASS - {name}")
            except Exception as exc:
                failed += 1
                print(f"Test {index}: FAIL - {name}\n  {type(exc).__name__}: {exc}")

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: JobPilot match API tests failed.")
        return 1

    print("SUCCESS: JobPilot match API tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())