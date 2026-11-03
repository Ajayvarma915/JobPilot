from __future__ import annotations

from app.api.main import (
    _candidate_experience_years,
    _extract_required_experience_years,
    _find_matching_location,
    _is_early_career_suitable,
    _is_target_software_role,
    _extract_salary_lpa,
    _compensation_signal,
    _maximum_early_career_years,
    _matches_requested_city,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_multi_city_location_matching() -> None:
    location = (
        "Bengaluru, Karnataka, India; Hyderabad, Telangana, India"
    )

    check(
        _matches_requested_city(location, "Bengaluru"),
        "A multi-city listing should match Bengaluru.",
    )

    check(
        _matches_requested_city(location, "Hyderabad"),
        "A multi-city listing should match Hyderabad.",
    )

    check(
        not _matches_requested_city(
            "Hyderabad, Telangana, India",
            "Bengaluru",
        ),
        "A Hyderabad-only listing must not match Bengaluru.",
    )

    check(
        not _matches_requested_city(
            "Bengaluru, Karnataka, India",
            "Hyderabad",
        ),
        "A Bengaluru-only listing must not match Hyderabad.",
    )

    check(
        _matches_requested_city(
            "Bengaluru, Karnataka, India",
            "Bangalore",
        ),
        "Bangalore and Bengaluru should be treated as aliases.",
    )

    matched = _find_matching_location(location, "Bengaluru")

    check(
        matched == "Bengaluru, Karnataka, India",
        f"Expected only the matching city for display, got {matched!r}.",
    )


def test_india_country_filter() -> None:
    check(
        _find_matching_location("Hyderabad, Telangana, India", "India")
        == "Hyderabad, Telangana, India",
        "An Indian city listing should match the India country filter.",
    )

    check(
        _find_matching_location(
            "Remote - India; Mumbai, Maharashtra, India",
            "India",
        )
        == "Remote - India",
        "Explicit India-remote roles should match the India filter.",
    )

    check(
        _find_matching_location("Remote", "India") == "Remote",
        "A generic Remote listing should be discoverable per user preference.",
    )

    check(
        _find_matching_location("Fully Remote", "India") == "Fully Remote",
        "Clearly global remote labels should match the India default.",
    )

    check(
        _find_matching_location("Remote - Brazil", "India") is None,
        "A Brazil-restricted remote listing must not match the India filter.",
    )

    check(
        _find_matching_location("Remote, United States", "India") is None,
        "A US-restricted remote listing must not match the India filter.",
    )

    check(
        _find_matching_location("São Paulo, Brazil", "India") is None,
        "Brazil-only onsite listings must not match the India filter.",
    )

    check(
        _find_matching_location(
            "Singapore; Bengaluru, Karnataka, India",
            "India",
        )
        == "Bengaluru, Karnataka, India",
        "Multi-location roles should match when at least one location is in India.",
    )


def test_experience_extraction() -> None:
    description = """
Minimum qualifications
Bachelor's degree or equivalent practical experience.
1 year of experience in software development.

Preferred qualifications
5 years of experience leading a large team.
"""

    extracted = _extract_required_experience_years(description)

    check(
        extracted == 1.0,
        f"Expected 1 year from minimum qualifications, got {extracted!r}.",
    )

    check(
        _candidate_experience_years() >= 1.0,
        "Candidate tenure should reflect the September 2025 TCS start date.",
    )

    check(
        _maximum_early_career_years() >= 1,
        "Maximum eligible experience should be at least one year.",
    )


def test_early_career_suitability() -> None:
    entry_role = _is_early_career_suitable(
        "Software Engineer II, Corp Eng",
        """
Minimum qualifications
Bachelor's degree.
1 year of experience in software development.
""",
    )

    check(
        entry_role,
        "A Software Engineer II role requiring one year should be eligible.",
    )

    stretch_role = _is_early_career_suitable(
        "Software Engineer III",
        """
Minimum qualifications
2 years of experience in software engineering.
""",
    )

    check(
        stretch_role
        == (_maximum_early_career_years() >= 2),
        "Two-year roles should follow the current early-career threshold.",
    )

    check(
        not _is_early_career_suitable(
            "Senior Software Engineer",
            "Bachelor's degree. 1 year of experience.",
        ),
        "Senior roles should be excluded by the default early-career filter.",
    )

    check(
        not _is_early_career_suitable(
            "Software Engineering Manager, Payments Platform",
            "Bachelor's degree. 1 year of experience.",
        ),
        "Management roles should be excluded.",
    )

    check(
        not _is_early_career_suitable(
            "Staff Software Engineer",
            """
Minimum qualifications
8 years of experience in software engineering.
""",
        ),
        "Staff roles with extensive experience requirements should be excluded.",
    )

    check(
        not _is_early_career_suitable(
            "Software Engineer, PhD, Early Career",
            """
Minimum qualifications
PhD degree in Computer Science.
""",
        ),
        "A PhD-required position should be excluded.",
    )

    check(
        not _is_early_career_suitable(
            "Software Engineering PhD Intern, Summer 2027",
            "Minimum qualifications: Bachelor's degree.",
        ),
        "Internship roles should be excluded for this employed-candidate workflow.",
    )


def test_target_role_scope() -> None:
    allowed = [
        "Software Engineer II, Corp Eng",
        "Software Development Engineer I",
        "Backend Engineer",
        "Frontend Developer",
        "Full Stack Software Engineer",
        "Platform Engineer",
        "Site Reliability Engineer",
        "Machine Learning Engineer",
        "Data Engineer",
        "SDET - Test Automation Engineer",
    ]
    blocked = [
        "Tech Support (Hybrid) (Fluent in English)",
        "SMB Account Executive (Hybrid)",
        "Talent Acquisition Partner",
        "Senior Commissions Analyst (Remote)",
        "Customer Support Engineer",
        "Technical Support Specialist",
        "Recruiter - Engineering",
    ]
    for title in allowed:
        check(_is_target_software_role(title), f"Expected software role to pass: {title}")
    for title in blocked:
        check(not _is_target_software_role(title), f"Non-software role leaked into feed: {title}")


def test_compensation_signal() -> None:
    check(_extract_salary_lpa("Compensation: INR 25-35 LPA") == (25.0, 35.0), "LPA range should be extracted")
    check(_extract_salary_lpa("CTC up to ₹30 LPA") == (30.0, 30.0), "Single LPA value should be extracted")
    check(_extract_salary_lpa("Salary competitive; market aligned") is None, "Undisclosed pay must stay unknown")
    check(_compensation_signal("Salary: 18-22 LPA")["status"] == "below_target", "Known below-target salary should be marked")
    check(_compensation_signal("CTC: 25-29 LPA")["status"] == "target_25_plus", "The 25-30 band should be labeled")
    check(_compensation_signal("CTC: 30-40 LPA")["status"] == "target_30_plus", "30+ band should be distinguished")
    check(_compensation_signal("Salary: 20-28 LPA")["status"] == "target_possible", "Overlapping range should be marked possible")
    check(_compensation_signal("Competitive compensation")["status"] == "not_disclosed", "Unknown salary should not be guessed")


def main() -> int:
    tests = [
        (
            "Multi-city location filtering and city aliases",
            test_multi_city_location_matching,
        ),
        (
            "India country and remote eligibility filtering",
            test_india_country_filter,
        ),
        (
            "Required experience extraction",
            test_experience_extraction,
        ),
        (
            "Early-career role suitability",
            test_early_career_suitability,
        ),
        (
            "Target software-engineering role scope",
            test_target_role_scope,
        ),
        (
            "Target compensation extraction and labels",
            test_compensation_signal,
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 68)
    print("JobPilot Job Filter Policy Tests")
    print("=" * 68)

    for number, (name, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {number}: PASS - {name}")
        except Exception as exc:
            failed += 1
            print(
                f"Test {number}: FAIL - {name}\n"
                f"  {type(exc).__name__}: {exc}"
            )

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: Job filter policy tests failed.")
        return 1

    print("SUCCESS: Job filter policy tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())