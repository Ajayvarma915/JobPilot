"""Tests for the central eligibility policy and the API's delegation to it."""
from __future__ import annotations

from app.api.main import (
    _extract_required_experience_years,
    _is_early_career_suitable,
    _is_target_software_role,
)
from app.services.jd_analyzer import JobDescriptionAnalyzer
from app.services.target_role_policy import (
    ELIGIBLE,
    ELIGIBLE_NEEDS_REVIEW,
    EXCLUDED,
    SOURCE_UNVERIFIED,
    early_career_title_exclusion,
    evaluate_eligibility,
    extract_minimum_experience_years,
    matches_software_role_family,
    requires_phd,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _job(**overrides):
    job = {
        "title": "Software Engineer",
        "description": "Minimum qualifications:\n1 year of experience in software development.",
        "location": ["Hyderabad, India"],
    }
    job.update(overrides)
    return job


def test_degree_length_is_not_experience() -> None:
    check(
        extract_minimum_experience_years(
            "Minimum qualifications\n4 year degree in CS or equivalent experience\n1 year of experience in Java"
        ) == 1.0,
        "A '4 year degree' must not be read as 4 years of experience.",
    )
    check(
        extract_minimum_experience_years("Basic qualifications\n- 4 year degree or 2 years of related experience") == 2.0,
        "The stated experience, not the degree length, must be used.",
    )
    check(extract_minimum_experience_years("Requirements\n1-3 years experience selling") == 1.0, "Ranges use the lower bound.")


def test_api_delegates_to_policy() -> None:
    desc = "Minimum qualifications\n1 year of experience.\nPreferred qualifications\nPhD preferred"
    check(_extract_required_experience_years(desc) == extract_minimum_experience_years(desc), "API experience must equal policy.")
    check(not _is_early_career_suitable("Software Engineer", "Minimum qualifications: PhD in Computer Science."),
          "Mandatory PhD must be excluded in the early-career feed.")
    check(_is_early_career_suitable("Software Engineer", desc), "Preferred-only PhD must not exclude.")
    check(not _is_early_career_suitable("Sr. Software Engineer", ""), "'Sr.' titles must be excluded by the shared seniority rule.")
    check(_is_early_career_suitable("Software Engineer III", "Minimum qualifications: 2 years of experience."),
          "Engineer III is judged by its stated requirement, not its number.")
    check(not _is_early_career_suitable("Software Engineer", "Minimum qualifications: 4 years of experience."),
          "More than the allowed years must be excluded.")
    for title in (
        "Product Security Engineer", "Cloud Security Engineer", "Threat Detection Engineer", "Backend Engineer",
        "Frontend Developer", "Back End Engineer", "Full-Stack Developer", "Software Security Engineer",
        "Test Automation Engineer", "SDET - Test Automation Engineer",
    ):
        check(_is_target_software_role(title), f"Technical role should pass: {title}")
        check(matches_software_role_family(title), f"Policy should agree: {title}")
    for title in ("Security Analyst", "SOC Analyst", "Account Executive", "Senior Commissions Analyst", ""):
        check(not _is_target_software_role(title), f"Non-engineering title must not pass: {title!r}")
    check(_is_target_software_role("Senior Software Engineer"), "Role-family test must not apply seniority (that is a separate rule).")
    check(early_career_title_exclusion("Senior Software Engineer") == "senior_or_lead_title", "Seniority rule is separate.")
    check(requires_phd("Minimum qualifications: PhD degree.") and not requires_phd("Preferred qualifications: PhD."), "PhD rule")


def test_decision_states() -> None:
    check(evaluate_eligibility(_job()).status == ELIGIBLE, "Clean job from a verified source should be eligible.")

    unverified = evaluate_eligibility(_job(), source_verified=False)
    check(unverified.status == SOURCE_UNVERIFIED, "Passing job from an unverified source must be source_unverified.")
    check("source_mapping_unverified_review" in unverified.flags, "Unverified source flag expected.")

    no_years = evaluate_eligibility(_job(description="Build services in Python."))
    check(no_years.status == ELIGIBLE_NEEDS_REVIEW and "minimum_experience_not_found_review" in no_years.flags,
          "Unstated experience must be reviewed, not guessed.")

    remote = evaluate_eligibility(_job(location=["Remote"]))
    check(remote.status == ELIGIBLE_NEEDS_REVIEW and "remote_country_eligibility_unverified" in remote.flags,
          "Plain remote must stay as a review item.")

    senior = evaluate_eligibility(_job(title="Senior Software Engineer"))
    check(senior.status == EXCLUDED and senior.reasons == ("senior_or_lead_title",), f"Got {senior}")

    abroad = evaluate_eligibility(_job(location=["Seattle, United States"]))
    check(abroad.status == EXCLUDED and "outside_india" in abroad.reasons, "Foreign-only location must be excluded with a reason.")

    too_senior = evaluate_eligibility(_job(description="Minimum qualifications:\n5 years of experience."))
    check(too_senior.status == EXCLUDED and too_senior.reasons[0].startswith("requires_5"), "Over-limit experience must be excluded.")

    # Unverified sources never hide an exclusion.
    check(evaluate_eligibility(_job(title="Account Executive"), source_verified=False).status == EXCLUDED,
          "Exclusion takes precedence over source_unverified.")
    # Undisclosed salary never changes the outcome.
    check(evaluate_eligibility(_job(salary=None)).status == ELIGIBLE, "Missing salary must not matter.")


def test_amazon_style_titles_and_business_domain_words() -> None:
    """Regression: Amazon's own entry-level titles were dropped as 'not a software role family', and a team
    name such as Finance or Supply Chain made a software engineer look non-software (found in a live sync)."""
    for title in ("Software Dev Engineer", "Software Dev Engineer II, Amazon India CFX team", "SDE2, Amazon Business - External Integrations",
                  "Software Development Engineer, Finance Technology", "Software Development Engineer II, Infrastructure Supply Chain Automation"):
        check(matches_software_role_family(title), f"{title!r} is a software role")
    for title in ("Finance Analyst", "Account Executive", "Marketing Engineer", "Technical Program Manager, Data Operations",
                  "Customer Engineer, Google Cloud", "Data Analyst, Risk"):
        check(not matches_software_role_family(title), f"{title!r} is not a software role")
    check(early_career_title_exclusion("Sr. Software Dev Engineer, Finance Technology") == "senior_or_lead_title", "seniority still applies")
    check(not _is_target_software_role("Manager, Software Development, Accounting Insights"), "managers are still excluded")


# Shortened from real postings that the earlier reader got wrong.
REAL_WORDINGS = (
    (3.0, "the word 'requirements' in a sentence is not the heading",
     "Key job responsibilities\n- Balance functional and non-functional requirements such as scale.\n- Own your responsibilities.\n"
     "Basic qualifications:\n- 3+ years of non-internship professional software development experience\n"
     "- 2+ years of non-internship design or architecture experience\nPreferred qualifications:\n- 5+ years of full life cycle experience"),
    (3.0, "'N+ years building' needs no word 'experience'",
     "What You will Need:\n\n3+ years building and shipping production frontend applications"),
    (5.0, "every requirement must be met, so the largest counts",
     "Requirements\nAt least 1 year of experience with Hybris\nAt least 3 years of experience with Angular\n"
     "At least 5 years of experience in building user interfaces"),
    (7.0, "a sentence naming preferred qualifications is not a preferred list",
     "The preferred qualifications are a bonus, not a requirement.\nMinimum requirements\n7+ years of industry software engineering experience\n"
     "Preferred qualifications\nExperience with payments"),
    (5.0, "a figure marked with > in brackets",
     "First-class understanding of NodeJs (>3 years)\nExcellent understanding of Redis (>5 years)"),
    (4.0, "a new part after an optional line is still read",
     "Good to have: Certification on GCP\n\nFunctional:\n\n4 to 5 years of relevant experience in cloud infrastructure"),
    (2.0, "an advanced-degree alternative does not lower the figure",
     "Minimum Qualifications\n2 years of experience with software development, or 1 year of experience with an advanced degree.\n"
     "Preferred Qualifications\n5 years of experience with data structures"),
    (2.0, "a range counts as its lower end",
     "Experience and Education\n2–5 years of experience\nin software engineering"),
    (None, "an optional list alone states no minimum",
     "Minimum Qualifications\nBachelor's degree.\nPreferred Qualifications\n5 years of experience with recommendation engines."),
    (None, "the employer's own history is not your experience",
     "The team has 50+ years of combined Machine Learning experience. In the last 5 years we grew to 9000 customers. "
     "We have 6+ years of experience serving brands. Applicants must be 18 years of age."),
)


def test_experience_wording_from_real_postings() -> None:
    for expected, why, text in REAL_WORDINGS:
        got = extract_minimum_experience_years(text)
        check(got == expected, f"{why}: expected {expected}, got {got}")
        check(JobDescriptionAnalyzer().analyze("Software Engineer", text).required_years_min == expected,
              f"the match score reads the same figure ({why})")


TESTS = [
    ("Experience is read correctly from real posting wording", test_experience_wording_from_real_postings),
    ("Amazon-style titles and business-domain words", test_amazon_style_titles_and_business_domain_words),
    ("Degree length is not experience", test_degree_length_is_not_experience),
    ("API delegates to the central policy", test_api_delegates_to_policy),
    ("Explicit eligibility states with reasons", test_decision_states),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
