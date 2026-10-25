from __future__ import annotations

from app.api.main import (
    _candidate_experience_years,
    _extract_required_experience_years,
    _find_matching_location,
    _is_early_career_suitable,
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
        _find_matching_location("Remote", "India") is None,
        "Unqualified remote roles must not be assumed to allow work from India.",
    )

    check(
        _find_matching_location("São Paulo, Brazil", "India") is None,
        "Brazil-only listings must not match the India filter.",
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