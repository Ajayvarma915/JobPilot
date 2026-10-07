from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Job
from app.services.job_normalizer import normalize_job


def run_unit_examples() -> None:
    """
    Test representative titles without external APIs.
    """

    examples = [
        {
            "title": "Software Engineer II, Corp Eng",
            "experience_level": "Early",
            "expected_role": "software_engineering",
            "expected_experience": "entry",
            "expected_engineering": True,
            "expected_management": False,
        },
        {
            "title": "Senior Software Engineer, AI/ML",
            "experience_level": "Mid",
            "expected_role": "ai_ml",
            "expected_experience": "senior",
            "expected_engineering": True,
            "expected_management": False,
        },
        {
            "title": "Staff Software Engineer, Google Cloud",
            "experience_level": "Advanced",
            "expected_role": "cloud_devops",
            "expected_experience": "staff",
            "expected_engineering": True,
            "expected_management": False,
        },
        {
            "title": "Software Engineering Manager",
            "experience_level": "Advanced",
            "expected_role": "management",
            "expected_experience": "manager",
            "expected_engineering": False,
            "expected_management": True,
        },
        {
            "title": "Software Engineering PhD Intern",
            "experience_level": "Early",
            "expected_role": "internship",
            "expected_experience": "intern",
            "expected_engineering": False,
            "expected_management": False,
        },
        {
            "title": "Silicon Engineering Intern, PhD",
            "experience_level": "Early",
            "expected_role": "internship",
            "expected_experience": "intern",
            "expected_engineering": False,
            "expected_management": False,
        },
        {
            "title": "Product Manager, Google Pay",
            "experience_level": "Advanced",
            "expected_role": "product",
            "expected_experience": "manager",
            "expected_engineering": False,
            "expected_management": True,
        },
        {
            "title": "Technical Program Manager, Cloud Storage",
            "experience_level": "Advanced",
            "expected_role": "program_management",
            "expected_experience": "manager",
            "expected_engineering": False,
            "expected_management": True,
        },
    ]

    print("========================================")
    print("Normalizer Unit Examples")
    print("========================================")

    passed = 0
    failed = 0

    for index, example in enumerate(
        examples,
        start=1,
    ):
        normalized = normalize_job(
            example
        )

        checks = {
            "role_family": (
                normalized.role_family
                == example["expected_role"]
            ),
            "experience": (
                normalized.normalized_experience
                == example["expected_experience"]
            ),
            "engineering": (
                normalized.is_engineering_role
                == example["expected_engineering"]
            ),
            "management": (
                normalized.is_management_role
                == example["expected_management"]
            ),
        }

        example_passed = all(
            checks.values()
        )

        if example_passed:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        print(
            f"{index:02d}. [{status}] "
            f"{normalized.title}"
        )
        print(
            f"    Role family  : "
            f"{normalized.role_family}"
        )
        print(
            f"    Experience   : "
            f"{normalized.normalized_experience}"
        )
        print(
            f"    Engineering? : "
            f"{normalized.is_engineering_role}"
        )
        print(
            f"    Management?  : "
            f"{normalized.is_management_role}"
        )
        print(
            f"    Technologies : "
            f"{', '.join(normalized.technologies) or 'None'}"
        )

        if not example_passed:
            print(
                f"    Checks       : "
                f"{checks}"
            )

        print()

    print(
        f"Unit tests: {passed} passed, "
        f"{failed} failed"
    )

    if failed:
        raise SystemExit(1)


def verify_database_jobs() -> None:
    """
    Run normalization against every job in SQLite.
    """

    db = SessionLocal()

    try:
        jobs = list(
            db.scalars(
                select(Job).order_by(
                    Job.id
                )
            )
        )

        print("========================================")
        print("Database Normalization Test")
        print("========================================")
        print(
            f"Jobs in database: {len(jobs)}"
        )
        print()

        if not jobs:
            print(
                "FAIL: Database contains no jobs."
            )
            raise SystemExit(1)

        normalized_jobs = []

        for job in jobs:
            normalized = normalize_job(job)

            if not normalized.title:
                raise AssertionError(
                    f"Job {job.id} has an "
                    "empty normalized title."
                )

            if normalized.role_family == "other":
                print(
                    f"WARNING: Generic role family "
                    f"for job {job.id}: "
                    f"{job.title}"
                )

            if normalized.normalized_experience == "unknown":
                print(
                    f"WARNING: Unknown experience "
                    f"for job {job.id}: "
                    f"{job.title}"
                )

            normalized_jobs.append(
                normalized
            )

        role_counts = Counter(
            job.role_family
            for job in normalized_jobs
        )

        experience_counts = Counter(
            job.normalized_experience
            for job in normalized_jobs
        )

        engineering_count = sum(
            1
            for job in normalized_jobs
            if job.is_engineering_role
        )

        management_count = sum(
            1
            for job in normalized_jobs
            if job.is_management_role
        )

        technology_counts = Counter()

        for job in normalized_jobs:
            technology_counts.update(
                job.technologies
            )

        print(
            f"Normalized jobs : "
            f"{len(normalized_jobs)}"
        )
        print(
            f"Engineering     : "
            f"{engineering_count}"
        )
        print(
            f"Management      : "
            f"{management_count}"
        )

        print()
        print("Role Families:")

        for name, count in sorted(
            role_counts.items()
        ):
            print(
                f"  {name:<22} {count}"
            )

        print()
        print("Experience:")

        for name, count in sorted(
            experience_counts.items()
        ):
            print(
                f"  {name:<22} {count}"
            )

        print()
        print("Top Technologies:")

        for name, count in (
            technology_counts
            .most_common(15)
        ):
            print(
                f"  {name:<22} {count}"
            )

        print()
        print(
            "SUCCESS: All database jobs "
            "were normalized successfully."
        )

    finally:
        db.close()


def main() -> None:
    run_unit_examples()
    verify_database_jobs()


if __name__ == "__main__":
    main()