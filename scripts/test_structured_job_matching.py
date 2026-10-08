from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.models import Job
from app.services.jd_analyzer import JobDescriptionAnalyzer
from app.services.job_matcher import JobMatcher


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "jobpilot.db"


def check(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def build_candidate_profile() -> SimpleNamespace:
    """
    Test representation of the current candidate profile.

    These values mirror the profile currently established for JobPilot.
    No additional unverified professional experience is added here.
    """

    return SimpleNamespace(
        education="BTech - Internet of Things (IoT), KL University",
        degree="bachelor",

        technical_skills=[
            "Java",
            "Python",
            "Data Structures and Algorithms",
            "Object Oriented Programming",
            "HTML",
            "CSS",
            "JavaScript",
            "Git",
            "GitHub",
            "React.js",
            "Tailwind CSS",
            "Next.js",
            "Chart.js",
            "Firebase",
            "Auth.js",
            "PyWhatKit",
            "NLP",
            "Machine Learning",
        ],

        programming_languages=[
            "Java",
            "Python",
            "JavaScript",
        ],

        frontend_skills=[
            "HTML",
            "CSS",
            "JavaScript",
            "React.js",
            "Tailwind CSS",
            "Next.js",
            "Chart.js",
        ],

        frameworks=[
            "React.js",
            "Next.js",
            "Tailwind CSS",
            "Auth.js",
        ],

        tools=[
            "Git",
            "GitHub",
            "Firebase",
            "Chart.js",
            "PyWhatKit",
        ],

        concepts=[
            "Data Structures and Algorithms",
            "OOP",
            "NLP",
            "Machine Learning",
            "Authentication",
            "Session Management",
            "CRUD",
        ],

        project_skills=[
            "React.js",
            "Next.js",
            "JavaScript",
            "Python",
            "Firebase",
            "Auth.js",
            "Chart.js",
            "NLP",
            "Machine Learning",
            "HTML",
            "CSS",
        ],

        internship_skills=[
            "HTML",
            "CSS",
            "JavaScript",
            "Frontend Development",
        ],

        target_role_families=[
            "software_engineering",
            "frontend",
            "full_stack",
        ],

        target_seniority=[
            "entry",
            "mid",
        ],

        target_locations=[
            "Hyderabad",
            "Bengaluru",
        ],

        years_of_experience=0.0,
        internship_experience=True,
    )


def test_structured_required_skills() -> None:
    profile = build_candidate_profile()

    job = SimpleNamespace(
        title="Software Engineer II",
        location="Hyderabad, Telangana, India",
        description="""
        Minimum Qualifications
        Bachelor's degree or equivalent practical experience.
        1 year of experience with software development in one
        or more programming languages, including Java and Python.
        Experience with JavaScript.

        Preferred Qualifications
        Experience with React.js.
        """,
        employment_type="Full-time",
    )

    matcher = JobMatcher(profile)

    result = matcher.match(job)

    check(
        result.recommendation
        in {
            "strong_match",
            "good_match",
        },
        "Entry-level software role should be a good/strong match.",
    )

    check(
        "Java" in result.matched_skills,
        "Java should match.",
    )

    check(
        "Python" in result.matched_skills,
        "Python should match.",
    )

    check(
        "JavaScript" in result.matched_skills,
        "JavaScript should match.",
    )

    check(
        "React.js" in result.matched_preferred_skills,
        "React.js should match preferred skills.",
    )

    check(
        result.required_years == 1.0,
        "Required experience should be 1 year.",
    )


def test_phd_is_hard_blocker() -> None:
    profile = build_candidate_profile()

    job = SimpleNamespace(
        title="Software Engineer, PhD",
        location="Hyderabad, Telangana, India",
        description="""
        Minimum Qualifications
        PhD degree in Computer Science or a related technical field.
        Experience with Python and Machine Learning.
        """,
        employment_type="Full-time",
    )

    matcher = JobMatcher(profile)

    result = matcher.match(job)

    check(
        result.score <= 35.0,
        "PhD requirement should cap the score.",
    )

    check(
        "PhD/doctorate requirement"
        in result.hard_constraints,
        "PhD constraint should be detected.",
    )

    check(
        result.recommendation == "low_match",
        "PhD-required job should be low match.",
    )


def test_manager_is_filtered() -> None:
    profile = build_candidate_profile()

    job = SimpleNamespace(
        title="Software Engineering Manager",
        location="Hyderabad, Telangana, India",
        description="""
        Minimum Qualifications
        Bachelor's degree or equivalent practical experience.
        8 years of experience in software engineering.
        Experience with Java and Python.
        """,
        employment_type="Full-time",
    )

    matcher = JobMatcher(profile)

    result = matcher.match(job)

    check(
        result.role_family == "management",
        "Manager role should be classified as management.",
    )

    check(
        result.score <= 35.0,
        "Management role should be capped.",
    )

    check(
        result.recommendation == "low_match",
        "Manager role should be low match.",
    )


def test_frontend_preferred_match() -> None:
    profile = build_candidate_profile()

    job = SimpleNamespace(
        title="Frontend Software Engineer",
        location="Bengaluru, Karnataka, India",
        description="""
        Minimum Qualifications
        Bachelor's degree.
        Experience with JavaScript and HTML.

        Preferred Qualifications
        Experience with React.js and CSS.
        """,
        employment_type="Full-time",
    )

    matcher = JobMatcher(profile)

    result = matcher.match(job)

    check(
        result.role_score == 25.0,
        "Frontend role should receive full role score.",
    )

    check(
        "JavaScript" in result.matched_skills,
        "JavaScript should match.",
    )

    check(
        "HTML" in result.matched_skills,
        "HTML should match.",
    )

    check(
        "React.js" in result.matched_preferred_skills,
        "React.js should match preferred skills.",
    )

    check(
        result.location_score == 5.0,
        "Bengaluru should receive location score.",
    )


def test_missing_required_skill() -> None:
    profile = build_candidate_profile()

    job = SimpleNamespace(
        title="Backend Software Engineer",
        location="Hyderabad, Telangana, India",
        description="""
        Minimum Qualifications
        Bachelor's degree.
        Experience with Node.js, MongoDB, Docker and Kubernetes.
        """,
        employment_type="Full-time",
    )

    matcher = JobMatcher(profile)

    result = matcher.match(job)

    check(
        "Node.js" in result.missing_required_skills,
        "Node.js should be missing from current profile.",
    )

    check(
        "MongoDB" in result.missing_required_skills,
        "MongoDB should be missing from current profile.",
    )

    check(
        "Docker" in result.missing_required_skills,
        "Docker should be missing from current profile.",
    )


def print_result(
    index: int,
    job: Job,
    result,
) -> None:
    print(
        f"{index:02d}. {result.score:5.1f}/100 | "
        f"{result.recommendation:<12} | "
        f"{job.title}"
    )

    print(
        f"    Role         : "
        f"{result.role_score:.1f}/25 "
        f"({result.role_family})"
    )

    print(
        f"    Seniority    : "
        f"{result.seniority_score:.1f}/20 "
        f"({result.seniority})"
    )

    print(
        f"    Experience   : "
        f"{result.experience_score:.1f}/20 "
        f"(required: {result.required_years})"
    )

    print(
        f"    Skills       : "
        f"{result.skills_score:.1f}/20"
    )

    print(
        f"    Education    : "
        f"{result.education_score:.1f}/10"
    )

    print(
        f"    Location     : "
        f"{result.location_score:.1f}/5"
    )

    print(
        "    Matched      : "
        + (
            ", ".join(result.matched_skills)
            if result.matched_skills
            else "None"
        )
    )

    print(
        "    Preferred    : "
        + (
            ", ".join(
                result.matched_preferred_skills
            )
            if result.matched_preferred_skills
            else "None"
        )
    )

    print(
        "    Missing      : "
        + (
            ", ".join(
                result.missing_required_skills
            )
            if result.missing_required_skills
            else "None"
        )
    )

    if result.concerns:
        print(
            "    Concerns     : "
            + " | ".join(result.concerns)
        )

    print()


def run_database_test() -> None:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DATABASE_PATH}"
        )

    engine = create_engine(
        f"sqlite:///{DATABASE_PATH.as_posix()}",
        future=True,
    )

    analyzer = JobDescriptionAnalyzer()
    profile = build_candidate_profile()
    matcher = JobMatcher(
        profile,
        analyzer=analyzer,
    )

    with Session(engine) as session:
        jobs = session.scalars(
            select(Job).order_by(Job.id)
        ).all()

    print()
    print("========================================")
    print("Structured Database Job Matching")
    print("========================================")
    print(
        f"Jobs in database: {len(jobs)}"
    )
    print()

    results = []

    for job in jobs:
        analysis = analyzer.analyze_job(
            job
        )

        result = matcher.match(
            job=job,
            analysis=analysis,
        )

        results.append(
            (job, result)
        )

    results.sort(
        key=lambda item: item[1].score,
        reverse=True,
    )

    print("Top Matches")
    print("----------------------------------------")

    for index, (job, result) in enumerate(
        results[:15],
        start=1,
    ):
        print_result(
            index,
            job,
            result,
        )

    print("All Jobs")
    print("----------------------------------------")

    for index, (job, result) in enumerate(
        results,
        start=1,
    ):
        print(
            f"{index:02d}. "
            f"{result.score:5.1f}/100 | "
            f"{result.recommendation:<12} | "
            f"{job.title}"
        )

    print()
    print("Recommendation Distribution")
    print("----------------------------------------")

    counts = {
        "strong_match": 0,
        "good_match": 0,
        "review": 0,
        "low_match": 0,
    }

    for _, result in results:
        counts[
            result.recommendation
        ] += 1

    for name in (
        "strong_match",
        "good_match",
        "review",
        "low_match",
    ):
        print(
            f"{name:15}: "
            f"{counts[name]}"
        )

    print()
    print("Match Range")
    print("----------------------------------------")

    if results:
        highest = results[0][1].score
        lowest = results[-1][1].score

        print(
            f"Highest score : {highest:.1f}/100"
        )
        print(
            f"Lowest score  : {lowest:.1f}/100"
        )

    print()
    print("========================================")

    if len(results) != len(jobs):
        print(
            "FAILURE: Not every database job received "
            "a structured match."
        )
        raise SystemExit(1)

    print(
        "SUCCESS: All database jobs received "
        "a structured JD-based match."
    )


def main() -> None:
    print("========================================")
    print("Structured Job Matcher Unit Tests")
    print("========================================")

    tests = [
        test_structured_required_skills,
        test_phd_is_hard_blocker,
        test_manager_is_filtered,
        test_frontend_preferred_match,
        test_missing_required_skill,
    ]

    passed = 0
    failed = 0

    for index, test_function in enumerate(
        tests,
        start=1,
    ):
        try:
            test_function()

            print(
                f"Test {index}: PASS"
            )

            passed += 1

        except Exception as exc:
            print(
                f"Test {index}: FAIL"
            )
            print(
                f"    {exc}"
            )
            print()

            failed += 1

    print()
    print("========================================")
    print(
        f"Unit tests: "
        f"{passed} passed, "
        f"{failed} failed"
    )
    print("========================================")

    if failed > 0:
        raise SystemExit(1)

    print(
        "SUCCESS: Structured matcher unit tests passed."
    )

    run_database_test()


if __name__ == "__main__":
    main()