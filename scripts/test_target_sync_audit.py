from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from app.services.target_role_policy import is_target_software_role
from scripts.sync_target_companies import _make_audit_row, write_audit_report


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_phd_targeted_titles_and_requirements_are_rejected() -> None:
    check(
        not is_target_software_role(
            "Software Engineer, PhD, Early Career, 2026",
            "Minimum qualifications: PhD in Computer Science.",
        )[0],
        "A PhD-targeted title must not pass the software job feed.",
    )
    check(
        not is_target_software_role(
            "Software Engineer",
            "Minimum qualifications: PhD degree in Computer Science.\n"
            "Preferred qualifications: experience with distributed systems.",
        )[0],
        "A PhD requirement inside minimum qualifications must be rejected.",
    )
    check(
        is_target_software_role(
            "Software Engineer",
            "Minimum qualifications: Bachelor's degree.\n"
            "Preferred qualifications: PhD preferred.",
        )[0],
        "A PhD listed only as preferred should not be treated as mandatory.",
    )


def test_audit_flags_missing_experience_and_ambiguous_remote() -> None:
    company = {
        "id": "sample",
        "name": "Sample Co",
        "integration": {"provider": "lever", "status": "active", "verified": True},
    }
    row = _make_audit_row(
        company,
        {
            "external_id": "job-1",
            "title": "Cloud Engineer",
            "url": "https://example.test/job-1",
            "location": ["Remote"],
            "description": "Build cloud platform services and internal tooling.",
        },
        2.0,
    )
    check(row["final_eligible"], "The reviewable cloud engineering role should remain discoverable.")
    check(row["audit_status"] == "eligible_needs_review", "Unclear role details should require manual review.")
    check("minimum_experience_not_found_review" in row["review_flags"], "Missing experience must be flagged.")
    check("remote_country_eligibility_unverified" in row["review_flags"], "Generic remote must be flagged.")
    check("broad_title_manual_review" in row["review_flags"], "Generic cloud engineer title must be flagged.")


def test_audit_csv_is_written_with_filter_reasons() -> None:
    company = {
        "id": "sample",
        "name": "Sample Co",
        "integration": {"provider": "greenhouse", "status": "active", "verified": True},
    }
    rows = [
        _make_audit_row(
            company,
            {
                "external_id": "job-2",
                "title": "Backend Engineer",
                "url": "https://example.test/job-2",
                "location": ["Hyderabad, India"],
                "description": "Minimum qualifications: 1 year of professional experience.",
            },
            2.0,
        ),
        _make_audit_row(
            company,
            {
                "external_id": "job-3",
                "title": "Software Engineer, PhD, Early Career",
                "url": "https://example.test/job-3",
                "location": ["India"],
                "description": "PhD in Computer Science required.",
            },
            2.0,
        ),
    ]
    with tempfile.TemporaryDirectory() as temp_dir:
        destination = write_audit_report(rows, Path(temp_dir) / "audit.csv")
        with destination.open("r", encoding="utf-8-sig", newline="") as handle:
            parsed = list(csv.DictReader(handle))
    check(len(parsed) == 2, "Audit report should contain every collected job.")
    check(parsed[0]["final_eligible"] == "True", "Eligible record should be preserved in report.")
    check(parsed[1]["final_eligible"] == "False", "Filtered record should be preserved in report.")
    check(parsed[1]["role_reason"] == "phd_required_or_phd_targeted_title", "Filter reason should be explicit.")


def main() -> int:
    tests = [
        ("PhD-targeted titles and requirements are excluded", test_phd_targeted_titles_and_requirements_are_rejected),
        ("Ambiguous experience and remote eligibility are flagged", test_audit_flags_missing_experience_and_ambiguous_remote),
        ("CSV audit report preserves eligibility decisions", test_audit_csv_is_written_with_filter_reasons),
    ]
    passed = failed = 0
    print("=" * 72)
    print("JobPilot Target Sync Audit Tests")
    print("=" * 72)
    for index, (label, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {index}: PASS - {label}")
        except Exception as exc:
            failed += 1
            print(f"Test {index}: FAIL - {label}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
