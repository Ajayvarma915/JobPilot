from __future__ import annotations

from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Job
from app.services.jd_analyzer import JobDescriptionAnalyzer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "jobpilot.db"


def main() -> None:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    database_url = (
        "sqlite:///"
        + DATABASE_PATH.as_posix()
    )

    engine = create_engine(
        database_url,
        future=True,
    )

    analyzer = JobDescriptionAnalyzer()

    with Session(engine) as session:
        jobs = session.scalars(
            select(Job).order_by(Job.id)
        ).all()

    print("========================================")
    print("Database JD Analysis")
    print("========================================")
    print(
        f"Database: {DATABASE_PATH}"
    )
    print(
        f"Jobs found: {len(jobs)}"
    )
    print()

    if not jobs:
        print(
            "WARNING: No jobs were found in the database."
        )
        return

    analyses = []

    required_skill_counter = Counter()
    preferred_skill_counter = Counter()
    technology_counter = Counter()

    confidence_counter = Counter()
    education_counter = Counter()
    hard_constraint_counter = Counter()

    jobs_with_required_years = 0
    jobs_with_preferred_years = 0
    jobs_with_responsibilities = 0
    jobs_with_required_skills = 0
    jobs_with_preferred_skills = 0
    jobs_with_education = 0
    jobs_with_hard_constraints = 0

    failures = []

    for job in jobs:
        try:
            analysis = analyzer.analyze_job(job)

            analyses.append(
                (job, analysis)
            )

            confidence_counter[analysis.confidence] += 1

            for skill in analysis.required_skills:
                required_skill_counter[skill] += 1

            for skill in analysis.preferred_skills:
                preferred_skill_counter[skill] += 1

            for technology in analysis.technologies:
                technology_counter[technology] += 1

            for education in analysis.required_education:
                education_counter[education] += 1

            for constraint in analysis.hard_constraints:
                hard_constraint_counter[constraint] += 1

            if analysis.required_years_min is not None:
                jobs_with_required_years += 1

            if analysis.preferred_years_min is not None:
                jobs_with_preferred_years += 1

            if analysis.responsibilities:
                jobs_with_responsibilities += 1

            if analysis.required_skills:
                jobs_with_required_skills += 1

            if analysis.preferred_skills:
                jobs_with_preferred_skills += 1

            if analysis.required_education:
                jobs_with_education += 1

            if analysis.hard_constraints:
                jobs_with_hard_constraints += 1

        except Exception as exc:
            failures.append(
                (
                    job.id,
                    job.title,
                    str(exc),
                )
            )

    print("Job Analysis Results")
    print("----------------------------------------")

    for index, (job, analysis) in enumerate(
        analyses,
        start=1,
    ):
        required_skills = (
            ", ".join(analysis.required_skills)
            if analysis.required_skills
            else "None"
        )

        preferred_skills = (
            ", ".join(analysis.preferred_skills)
            if analysis.preferred_skills
            else "None"
        )

        education = (
            ", ".join(analysis.required_education)
            if analysis.required_education
            else "None"
        )

        constraints = (
            ", ".join(analysis.hard_constraints)
            if analysis.hard_constraints
            else "None"
        )

        print(
            f"{index:02d}. {job.title}"
        )
        print(
            f"    Confidence       : "
            f"{analysis.confidence}"
        )
        print(
            f"    Required years   : "
            f"{analysis.required_years_min}"
        )
        print(
            f"    Preferred years  : "
            f"{analysis.preferred_years_min}"
        )
        print(
            f"    Required skills  : "
            f"{required_skills}"
        )
        print(
            f"    Preferred skills : "
            f"{preferred_skills}"
        )
        print(
            f"    Education        : "
            f"{education}"
        )
        print(
            f"    Responsibilities : "
            f"{len(analysis.responsibilities)}"
        )
        print(
            f"    Hard constraints : "
            f"{constraints}"
        )
        print()

    print("========================================")
    print("Coverage Summary")
    print("========================================")

    total_jobs = len(jobs)

    print(
        f"Jobs analyzed successfully : "
        f"{len(analyses)}/{total_jobs}"
    )
    print(
        f"Analysis failures           : "
        f"{len(failures)}"
    )
    print(
        f"Required years extracted    : "
        f"{jobs_with_required_years}/{total_jobs}"
    )
    print(
        f"Preferred years extracted   : "
        f"{jobs_with_preferred_years}/{total_jobs}"
    )
    print(
        f"Required skills extracted   : "
        f"{jobs_with_required_skills}/{total_jobs}"
    )
    print(
        f"Preferred skills extracted  : "
        f"{jobs_with_preferred_skills}/{total_jobs}"
    )
    print(
        f"Education extracted         : "
        f"{jobs_with_education}/{total_jobs}"
    )
    print(
        f"Responsibilities extracted  : "
        f"{jobs_with_responsibilities}/{total_jobs}"
    )
    print(
        f"Hard constraints detected  : "
        f"{jobs_with_hard_constraints}/{total_jobs}"
    )

    print()
    print("Confidence Distribution")
    print("----------------------------------------")

    for confidence in ("high", "medium", "low"):
        print(
            f"{confidence:>7}: "
            f"{confidence_counter.get(confidence, 0)}"
        )

    print()
    print("Top Required Skills")
    print("----------------------------------------")

    if required_skill_counter:
        for skill, count in required_skill_counter.most_common(15):
            print(
                f"{skill:35} {count}"
            )
    else:
        print("None")

    print()
    print("Top Preferred Skills")
    print("----------------------------------------")

    if preferred_skill_counter:
        for skill, count in preferred_skill_counter.most_common(15):
            print(
                f"{skill:35} {count}"
            )
    else:
        print("None")

    print()
    print("Top Technologies")
    print("----------------------------------------")

    if technology_counter:
        for skill, count in technology_counter.most_common(20):
            print(
                f"{skill:35} {count}"
            )
    else:
        print("None")

    print()
    print("Required Education")
    print("----------------------------------------")

    if education_counter:
        for education, count in education_counter.items():
            print(
                f"{education:35} {count}"
            )
    else:
        print("None")

    print()
    print("Hard Constraints")
    print("----------------------------------------")

    if hard_constraint_counter:
        for constraint, count in hard_constraint_counter.items():
            print(
                f"{constraint:50} {count}"
            )
    else:
        print("None")

    if failures:
        print()
        print("Failures")
        print("----------------------------------------")

        for job_id, title, error in failures:
            print(
                f"Job {job_id}: {title}"
            )
            print(
                f"    Error: {error}"
            )

    print()
    print("========================================")

    if failures:
        print(
            "FAILURE: One or more database JDs "
            "could not be analyzed."
        )
        raise SystemExit(1)

    if len(analyses) != total_jobs:
        print(
            "FAILURE: Not every database job "
            "received an analysis."
        )
        raise SystemExit(1)

    print(
        "SUCCESS: All database jobs received "
        "a JD analysis."
    )


if __name__ == "__main__":
    main()