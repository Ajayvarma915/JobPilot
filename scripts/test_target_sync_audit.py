from __future__ import annotations

import csv
import tempfile
from pathlib import Path

from app.services.target_role_policy import (
    extract_minimum_experience_years,
    is_india_or_remote_eligible,
    is_target_software_role,
)
from scripts import sync_target_companies as sync_module
from scripts.sync_target_companies import (
    _make_audit_row,
    _mark_possible_duplicates,
    write_audit_report,
)


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



def test_amazon_qualification_experience_format() -> None:
    description = """
Basic Qualifications
- 3+ years of non-internship professional software development experience
- Experience with distributed systems.
"""
    check(
        extract_minimum_experience_years(description) == 3.0,
        "Amazon's 'non-internship professional software development experience' wording must be parsed.",
    )
    accepted, reason = is_target_software_role(
        "Software Development Engineer",
        description,
        maximum_required_years=2.0,
    )
    check(not accepted and reason == "requires_3_years", "A 3-year minimum must be excluded from a 2-year target.")


def test_years_in_named_role_are_parsed() -> None:
    description = (
        "Minimum Qualifications: Bachelor's degree in Engineering or Computer Science. "
        "4 years in a Salesforce Developer or Architect role. "
        "Experience working with Salesforce and application development."
    )
    check(
        extract_minimum_experience_years(description) == 4.0,
        "A stated duration in a named role must be parsed even without the word experience.",
    )
    accepted, reason = is_target_software_role(
        "Salesforce Application Engineer", description, maximum_required_years=2.0
    )
    check(
        not accepted and reason == "requires_4_years",
        "A four-year requirement must be filtered out of a two-year search.",
    )


def test_engineer_level_iii_uses_explicit_experience_requirement() -> None:
    within_limit = (
        "Minimum qualifications: Bachelor's degree and 2 years of software development experience."
    )
    accepted, reason = is_target_software_role(
        "Software Engineer III, Core Systems", within_limit, maximum_required_years=2.0
    )
    check(
        accepted and reason == "eligible_software_role",
        "Engineer III should remain eligible when the explicit minimum is within two years.",
    )
    above_limit = "Minimum qualifications: 3 years of software development experience."
    accepted, reason = is_target_software_role(
        "Software Engineer III, Core Systems", above_limit, maximum_required_years=2.0
    )
    check(
        not accepted and reason == "requires_3_years",
        "Engineer III must still be excluded when the stated minimum exceeds two years.",
    )
    check(
        not is_target_software_role(
            "Senior Software Engineer III", within_limit, maximum_required_years=2.0
        )[0],
        "The explicit senior title must continue to be excluded.",
    )


def test_iso_country_codes_and_country_names() -> None:
    check(
        is_india_or_remote_eligible({"location": ["IN, TS, Hyderabad"]}) == (True, "india_location"),
        "IN country-code location should be recognized as India.",
    )
    check(
        is_india_or_remote_eligible({"location": ["US, WA, Seattle"]}) == (False, "outside_india"),
        "US country-code location should be explicitly outside India.",
    )
    check(
        is_india_or_remote_eligible({"location": ["IE, D, Dublin"]}) == (False, "outside_india"),
        "IE country-code location should be explicitly outside India.",
    )
    check(
        is_india_or_remote_eligible({"location": ["Taipei City, Taiwan"]}) == (False, "outside_india"),
        "Taiwan location should be explicitly outside India.",
    )


def test_review_rows_are_not_auto_sync_eligible() -> None:
    company = {
        "id": "sample",
        "name": "Sample Co",
        "integration": {"provider": "lever", "status": "active", "verified": True},
    }
    row = _make_audit_row(
        company,
        {
            "external_id": "review-1",
            "title": "Cloud AI Engineer (English)",
            "url": "https://example.test/review-1",
            "location": ["Bengaluru, India"],
            "description": "Build AI solutions for cloud customers.",
        },
        2.0,
    )
    check(row["final_eligible"], "The potential role should remain visible for review.")
    check(row["audit_status"] == "eligible_needs_review", "Broad Cloud AI title should require review.")
    check(not row["auto_sync_eligible"], "Review-pending rows must not be auto-synced.")
    check(
        "broad_title_manual_review" in row["review_flags"],
        "Broad Cloud AI title should carry a review flag.",
    )


def test_probable_duplicate_rows_are_flagged_not_removed() -> None:
    company = {
        "id": "sample",
        "name": "Sample Co",
        "integration": {"provider": "lever", "status": "active", "verified": True},
    }
    jobs = [
        {"external_id": "a", "title": "SDE II, AB Mobile", "url": "https://example.test/a",
         "location": ["Hyderabad, India"], "description": "Minimum qualifications: 1 year of software development experience. Build mobile shopping."},
        {"external_id": "b", "title": "SDE-II, AB Mobile", "url": "https://example.test/b",
         "location": ["Hyderabad, India"], "description": "Minimum qualifications: 1 year of software development experience. Build mobile shopping."},
    ]
    rows = [_make_audit_row(company, job, 2.0) for job in jobs]
    _mark_possible_duplicates(rows)
    check(len(rows) == 2, "Potential duplicates must not be silently removed.")
    check(
        all(row["possible_duplicate_group_size"] == 2 for row in rows),
        "Both likely duplicate postings should share a group size of two.",
    )
    check(
        all(not row["auto_sync_eligible"] for row in rows),
        "Possible duplicates must be held for review instead of auto-sync.",
    )



def test_live_sync_writes_only_fully_eligible_jobs() -> None:
    class FakeCollector:
        def collect(self):
            return [
                {
                    "external_id": "approved-1",
                    "title": "Backend Engineer",
                    "url": "https://example.test/approved-1",
                    "location": ["Hyderabad, India"],
                    "description": "Minimum qualifications: 1 year of software development experience.",
                },
                {
                    "external_id": "review-1",
                    "title": "Cloud AI Engineer (English)",
                    "url": "https://example.test/review-1",
                    "location": ["Hyderabad, India"],
                    "description": "Build AI solutions for cloud customers.",
                },
            ]

    class FakeDB:
        def __init__(self):
            self.committed = False
            self.closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

        def close(self):
            self.closed = True

    class FakeRepository:
        def __init__(self):
            self.upserted_titles = []

        def get_or_create_company(self, **kwargs):
            return {"name": kwargs["name"]}

        def upsert_job(self, company, job_data):
            self.upserted_titles.append(job_data["title"])
            return object(), True

    company = {
        "id": "sample",
        "name": "Sample Co",
        "website": "https://example.test",
        "careers_url": "https://example.test/careers",
        "integration": {
            "provider": "lever",
            "status": "active",
            "verified": True,
            "settings": {"site": "sample"},
        },
    }
    fake_db = FakeDB()
    fake_repo = FakeRepository()

    original_make_collector = sync_module._make_collector
    original_session_local = sync_module.SessionLocal
    original_repository = sync_module.JobRepository
    try:
        sync_module._make_collector = lambda _company: FakeCollector()
        sync_module.SessionLocal = lambda: fake_db
        sync_module.JobRepository = lambda _db: fake_repo

        result = sync_module.sync_company(
            company,
            dry_run=False,
            maximum_required_years=2.0,
        )
    finally:
        sync_module._make_collector = original_make_collector
        sync_module.SessionLocal = original_session_local
        sync_module.JobRepository = original_repository

    check(result.eligible == 2, "Both rows should pass the initial role/location screen.")
    check(result.auto_sync_eligible == 1, "Only one row should be auto-sync eligible.")
    check(result.review_required == 1, "One row should remain pending manual review.")
    check(result.inserted == 1, "Only the fully eligible job should be inserted.")
    check(
        fake_repo.upserted_titles == ["Backend Engineer"],
        f"Review-pending jobs must not be written, got {fake_repo.upserted_titles!r}.",
    )
    check(fake_db.committed and fake_db.closed, "The successful safe upsert should commit and close the fake DB.")



def test_unverified_source_mapping_blocks_auto_sync() -> None:
    company = {
        "id": "sample",
        "name": "Sample Co",
        "integration": {
            "provider": "greenhouse",
            "status": "configured_needs_live_validation",
            "verified": False,
        },
    }
    row = _make_audit_row(
        company,
        {
            "external_id": "unverified-1",
            "title": "Frontend Engineer",
            "url": "https://example.test/unverified-1",
            "location": ["Bengaluru, India"],
            "description": "Minimum qualifications: 1 year of frontend software development experience.",
        },
        2.0,
    )
    check(row["final_eligible"], "The job should remain visible as a candidate.")
    check(row["audit_status"] == "eligible_needs_review", "Unverified source mapping must require review.")
    check(not row["auto_sync_eligible"], "Unverified source mappings must not be auto-sync eligible.")
    check(
        "source_mapping_unverified_review" in row["review_flags"],
        "The report should explain why the source is held.",
    )


def main() -> int:
    tests = [
        ("PhD-targeted titles and requirements are excluded", test_phd_targeted_titles_and_requirements_are_rejected),
        ("Ambiguous experience and remote eligibility are flagged", test_audit_flags_missing_experience_and_ambiguous_remote),
        ("CSV audit report preserves eligibility decisions", test_audit_csv_is_written_with_filter_reasons),
        ("Amazon qualification experience wording is parsed", test_amazon_qualification_experience_format),
        ("Years in a named role are parsed", test_years_in_named_role_are_parsed),
        ("Engineer III follows the explicit experience requirement", test_engineer_level_iii_uses_explicit_experience_requirement),
        ("ISO country codes and names are classified", test_iso_country_codes_and_country_names),
        ("Review-pending rows are blocked from auto-sync", test_review_rows_are_not_auto_sync_eligible),
        ("Probable duplicate rows are flagged, not removed", test_probable_duplicate_rows_are_flagged_not_removed),
        ("Live sync writes only fully eligible jobs", test_live_sync_writes_only_fully_eligible_jobs),
        ("Unverified source mapping blocks automatic sync", test_unverified_source_mapping_blocks_auto_sync),
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
