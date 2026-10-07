from __future__ import annotations

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Job
from app.profile.candidate_profile import (
    get_candidate_profile,
)
from app.services.job_matcher import match_job
from app.services.job_normalizer import normalize_job


def run_unit_examples() -> None:
    print("========================================")
    print("Job Matcher Unit Examples")
    print("========================================")

    candidate = get_candidate_profile()

    examples = [
        {
            "title": "Software Engineer I, Hyderabad",
            "description": (
                "Minimum Qualifications\n"
                "Bachelor's degree or equivalent practical experience.\n"
                "Knowledge of Java and Python.\n"
                "Experience with software development.\n"
            ),
            "experience_level": "Early",
            "location": ["Hyderabad, Telangana, India"],
        },
        {
            "title": "Frontend Software Engineer",
            "description": (
                "Minimum Qualifications\n"
                "Bachelor's degree or equivalent practical experience.\n"
                "Experience with JavaScript, React.js, HTML and CSS.\n"
            ),
            "experience_level": "Early",
            "location": ["Hyderabad, Telangana, India"],
        },
        {
            "title": "Staff Software Engineer, Google Cloud",
            "description": (
                "Minimum Qualifications\n"
                "Bachelor's degree or equivalent practical experience.\n"
                "8 years of experience in software development.\n"
                "Experience with distributed systems.\n"
            ),
            "experience_level": "Advanced",
            "location": ["Hyderabad, Telangana, India"],
        },
        {
            "title": "Software Engineering Manager",
            "description": (
                "Minimum Qualifications\n"
                "Bachelor's degree or equivalent practical experience.\n"
                "8 years of experience in software development.\n"
            ),
            "experience_level": "Advanced",
            "location": ["Hyderabad, Telangana, India"],
        },
        {
            "title": "Software Engineer, PhD",
            "description": (
                "Minimum Qualifications\n"
                "PhD degree in Computer Science or a related field.\n"
                "Experience with Python and machine learning.\n"
            ),
            "experience_level": "Mid",
            "location": ["Hyderabad, Telangana, India"],
        },
    ]

    passed = 0
    failed = 0

    for index, example in enumerate(
        examples,
        start=1,
    ):
        normalized = normalize_job(
            example
        )

        result = match_job(
            job=normalized,
            candidate=candidate,
            description=example["description"],
        )

        print(
            f"{index:02d}. {example['title']}"
        )
        print(
            f"    Score          : {result.score}/100"
        )
        print(
            f"    Recommendation : "
            f"{result.recommendation}"
        )
        print(
            f"    Role           : "
            f"{result.role_score}/25"
        )
        print(
            f"    Seniority      : "
            f"{result.seniority_score}/20"
        )
        print(
            f"    Experience     : "
            f"{result.experience_score}/20"
        )
        print(
            f"    Skills         : "
            f"{result.skills_score}/20"
        )
        print(
            f"    Education      : "
            f"{result.education_score}/10"
        )
        print(
            f"    Location       : "
            f"{result.location_score}/5"
        )
        print(
            f"    Skills matched : "
            f"{', '.join(result.matched_skills) or 'None'}"
        )

        # Basic semantic expectations.
        checks = []

        if "Manager" in example["title"]:
            checks.append(
                result.recommendation
                in {
                    "low_match",
                    "review",
                }
            )

        elif "Staff" in example["title"]:
            checks.append(
                result.recommendation
                in {
                    "low_match",
                    "review",
                }
            )

        elif "PhD" in example["title"]:
            checks.append(
                result.score <= 35
            )

        else:
            checks.append(
                result.score > 50
            )

        if all(checks):
            passed += 1
            print("    Test           : PASS")
        else:
            failed += 1
            print("    Test           : FAIL")

        print()

    print(
        f"Unit tests: {passed} passed, "
        f"{failed} failed"
    )

    if failed:
        raise SystemExit(1)


def run_database_scoring() -> None:
    print("========================================")
    print("Database Job Matching")
    print("========================================")

    candidate = get_candidate_profile()

    db = SessionLocal()

    try:
        jobs = list(
            db.scalars(
                select(Job).order_by(
                    Job.id
                )
            )
        )

        print(
            f"Jobs in database: {len(jobs)}"
        )
        print()

        if not jobs:
            print(
                "FAIL: Database contains no jobs."
            )
            raise SystemExit(1)

        scored_jobs = []

        for job in jobs:
            normalized = normalize_job(
                job
            )

            result = match_job(
                job=normalized,
                candidate=candidate,
                description=job.description,
            )

            scored_jobs.append(
                (
                    job,
                    normalized,
                    result,
                )
            )

        scored_jobs.sort(
            key=lambda item: item[2].score,
            reverse=True,
        )

        print("Top Matches:")
        print("----------------------------------------")

        for rank, (
            job,
            normalized,
            result,
        ) in enumerate(
            scored_jobs[:10],
            start=1,
        ):
            print(
                f"{rank:02d}. "
                f"{result.score:>5.1f}/100 "
                f"{job.title}"
            )
            print(
                f"    Role           : "
                f"{normalized.role_family}"
            )
            print(
                f"    Experience     : "
                f"{normalized.normalized_experience}"
            )
            print(
                f"    Recommendation : "
                f"{result.recommendation}"
            )
            print(
                f"    Skills         : "
                f"{', '.join(result.matched_skills) or 'None'}"
            )
            print()

        print("All Jobs:")
        print("----------------------------------------")

        for index, (
            job,
            normalized,
            result,
        ) in enumerate(
            scored_jobs,
            start=1,
        ):
            print(
                f"{index:02d}. "
                f"{result.score:>5.1f}/100 | "
                f"{result.recommendation:<12} | "
                f"{job.title}"
            )

        print()
        print(
            "SUCCESS: All database jobs "
            "received a relevance score."
        )

    finally:
        db.close()


def main() -> None:
    run_unit_examples()
    print()
    run_database_scoring()


if __name__ == "__main__":
    main()