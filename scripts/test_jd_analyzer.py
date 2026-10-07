from app.services.jd_analyzer import JobDescriptionAnalyzer


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_google_style_software_engineer() -> None:
    title = "Software Engineer I"

    description = """
    About the job
    Build scalable backend services and collaborate with engineers
    to deliver reliable products.

    Minimum qualifications
    Bachelor's degree in Computer Science or a related field.
    1 year of experience with software development.
    Experience with Java or Python.
    Experience with JavaScript and SQL.

    Preferred qualifications
    Experience with React.js.
    Familiarity with Google Cloud.
    2+ years of experience is a plus.

    Responsibilities
    Design and implement software features.
    Debug production issues.
    Collaborate with cross-functional teams.
    """

    analyzer = JobDescriptionAnalyzer()

    result = analyzer.analyze(
        title=title,
        description=description,
        location="Hyderabad, Telangana, India",
        employment_type="Full-time",
    )

    check(
        "Java" in result.required_skills,
        "Java should be a required skill.",
    )

    check(
        "Python" in result.required_skills,
        "Python should be a required skill.",
    )

    check(
        "JavaScript" in result.required_skills,
        "JavaScript should be a required skill.",
    )

    check(
        "SQL" in result.required_skills,
        "SQL should be a required skill.",
    )

    check(
        "React.js" in result.preferred_skills,
        "React.js should be a preferred skill.",
    )

    check(
        "React.js" not in result.required_skills,
        "React.js should not be required.",
    )

    check(
        "Google Cloud" in result.preferred_skills,
        "Google Cloud should be a preferred skill.",
    )

    check(
        "Google Cloud" not in result.required_skills,
        "Google Cloud should not be required.",
    )

    check(
        result.required_years_min == 1.0,
        f"Expected 1 year required, got {result.required_years_min}",
    )

    check(
        result.preferred_years_min == 2.0,
        f"Expected 2 years preferred, got {result.preferred_years_min}",
    )

    check(
        "bachelor" in result.required_education,
        "Bachelor degree should be required.",
    )

    check(
        result.employment_type == "Full-time",
        "Provided employment type should be preserved.",
    )

    check(
        "Hyderabad, Telangana, India" in result.location_requirements,
        "Location should be preserved.",
    )

    check(
        len(result.responsibilities) >= 2,
        "Responsibilities should be extracted.",
    )

    check(
        result.confidence == "high",
        f"Expected high confidence, got {result.confidence}",
    )


def test_phd_requirement() -> None:
    title = "Software Engineer, PhD, Early Career"

    description = """
    About the job
    Work on advanced machine learning systems.

    Minimum qualifications
    PhD in Computer Science, Machine Learning, or a related field.
    Experience with Python and Machine Learning.

    Responsibilities
    Develop machine learning systems.
    """

    analyzer = JobDescriptionAnalyzer()

    result = analyzer.analyze(
        title=title,
        description=description,
        location="Mountain View, CA",
    )

    check(
        "phd" in result.required_education,
        "PhD should be detected as required.",
    )

    check(
        "Python" in result.required_skills,
        "Python should be required.",
    )

    check(
        "Machine Learning" in result.required_skills,
        "Machine Learning should be required.",
    )

    check(
        "PhD/doctorate requirement" in result.hard_constraints,
        "PhD should be marked as a hard constraint.",
    )


def test_manager_job_experience() -> None:
    title = "Software Engineering Manager"

    description = """
    About the job
    Lead an engineering team delivering large-scale systems.

    Minimum qualifications
    Bachelor's degree in Computer Science or equivalent.
    8+ years of experience in software engineering.
    3+ years of experience managing engineers.
    Experience with Java and Python.

    Preferred qualifications
    Experience with cloud infrastructure.
    """

    analyzer = JobDescriptionAnalyzer()

    result = analyzer.analyze(
        title=title,
        description=description,
    )

    check(
        result.required_years_min == 8.0,
        f"Expected 8 years required, got {result.required_years_min}",
    )

    check(
        "Java" in result.required_skills,
        "Java should be required.",
    )

    check(
        "Python" in result.required_skills,
        "Python should be required.",
    )

    check(
        "Google Cloud" not in result.preferred_skills,
        "Google Cloud should not be invented.",
    )


def test_internship_detection() -> None:
    title = "Software Engineering Intern"

    description = """
    About the job
    Join our engineering team for a summer internship.

    Minimum qualifications
    Currently pursuing a Bachelor's degree.
    Knowledge of Python and JavaScript.

    Preferred qualifications
    Experience with React.js.

    Responsibilities
    Write software under the guidance of senior engineers.
    """

    analyzer = JobDescriptionAnalyzer()

    result = analyzer.analyze(
        title=title,
        description=description,
    )

    check(
        result.employment_type == "internship",
        f"Expected internship, got {result.employment_type}",
    )

    check(
        "Internship role" in result.hard_constraints,
        "Internship should be listed as a hard constraint.",
    )

    check(
        "Python" in result.required_skills,
        "Python should be required.",
    )

    check(
        "JavaScript" in result.required_skills,
        "JavaScript should be required.",
    )

    check(
        "React.js" in result.preferred_skills,
        "React.js should be preferred.",
    )

    check(
        "React.js" not in result.required_skills,
        "React.js should not be required.",
    )


def test_unstructured_jd() -> None:
    title = "Backend Engineer"

    description = """
    We are looking for a backend engineer with 3+ years of experience
    building REST APIs using Node.js and MongoDB. Experience with Docker
    is required. Familiarity with AWS is a plus.
    """

    analyzer = JobDescriptionAnalyzer()

    result = analyzer.analyze(
        title=title,
        description=description,
        location="Bengaluru, Karnataka, India",
    )

    check(
        result.required_years_min == 3.0,
        f"Expected 3 years, got {result.required_years_min}",
    )

    check(
        "Node.js" in result.required_skills,
        "Node.js should be detected as required.",
    )

    check(
        "MongoDB" in result.required_skills,
        "MongoDB should be detected as required.",
    )

    check(
        "Docker" in result.required_skills,
        "Docker should be required.",
    )

    check(
        "AWS" in result.preferred_skills,
        "AWS should be preferred.",
    )

    check(
        "AWS" not in result.required_skills,
        "AWS should not be required.",
    )

    check(
        "Bengaluru, Karnataka, India" in result.location_requirements,
        "Location should be preserved.",
    )


def print_result(
    number: int,
    result,
) -> None:
    print(f"{number:02d}. {result.title}")
    print(
        f"    Confidence       : "
        f"{result.confidence}"
    )
    print(
        f"    Required years   : "
        f"{result.required_years_min}"
    )
    print(
        f"    Preferred years  : "
        f"{result.preferred_years_min}"
    )
    print(
        "    Required skills  : "
        + (
            ", ".join(result.required_skills)
            if result.required_skills
            else "None"
        )
    )
    print(
        "    Preferred skills : "
        + (
            ", ".join(result.preferred_skills)
            if result.preferred_skills
            else "None"
        )
    )
    print(
        "    Education        : "
        + (
            ", ".join(result.required_education)
            if result.required_education
            else "None"
        )
    )
    print(
        "    Hard constraints : "
        + (
            ", ".join(result.hard_constraints)
            if result.hard_constraints
            else "None"
        )
    )
    print()


def main() -> None:
    print("========================================")
    print("JD Analyzer Unit Examples")
    print("========================================")

    tests = [
        test_google_style_software_engineer,
        test_phd_requirement,
        test_manager_job_experience,
        test_internship_detection,
        test_unstructured_jd,
    ]

    passed = 0
    failed = 0

    for index, test_function in enumerate(
        tests,
        start=1,
    ):
        try:
            test_function()

            analyzer = JobDescriptionAnalyzer()

            if index == 1:
                result = analyzer.analyze(
                    title="Software Engineer I",
                    description="""
                    About the job
                    Build scalable backend services.

                    Minimum qualifications
                    Bachelor's degree.
                    1 year of experience with software development.
                    Experience with Java or Python.
                    Experience with JavaScript and SQL.

                    Preferred qualifications
                    Experience with React.js.
                    Familiarity with Google Cloud.
                    2+ years of experience is a plus.

                    Responsibilities
                    Design and implement software features.
                    Debug production issues.
                    """,
                    location="Hyderabad, Telangana, India",
                    employment_type="Full-time",
                )

            elif index == 2:
                result = analyzer.analyze(
                    title="Software Engineer, PhD, Early Career",
                    description="""
                    Minimum qualifications
                    PhD in Computer Science.
                    Experience with Python and Machine Learning.

                    Responsibilities
                    Develop machine learning systems.
                    """,
                    location="Mountain View, CA",
                )

            elif index == 3:
                result = analyzer.analyze(
                    title="Software Engineering Manager",
                    description="""
                    Minimum qualifications
                    Bachelor's degree.
                    8+ years of experience in software engineering.
                    3+ years of experience managing engineers.
                    Experience with Java and Python.
                    """,
                )

            elif index == 4:
                result = analyzer.analyze(
                    title="Software Engineering Intern",
                    description="""
                    Minimum qualifications
                    Currently pursuing a Bachelor's degree.
                    Knowledge of Python and JavaScript.

                    Preferred qualifications
                    Experience with React.js.

                    Responsibilities
                    Write software under the guidance of senior engineers.
                    """,
                )

            else:
                result = analyzer.analyze(
                    title="Backend Engineer",
                    description="""
                    We are looking for a backend engineer with 3+ years
                    of experience building REST APIs using Node.js and
                    MongoDB. Experience with Docker is required.
                    Familiarity with AWS is a plus.
                    """,
                    location="Bengaluru, Karnataka, India",
                )

            print_result(
                index,
                result,
            )

            print(
                f"Test {index}: PASS\n"
            )

            passed += 1

        except Exception as exc:
            print(
                f"Test {index}: FAIL\n"
                f"    {exc}\n"
            )
            failed += 1

    print("========================================")
    print(
        f"Unit tests: {passed} passed, {failed} failed"
    )
    print("========================================")

    if failed > 0:
        raise SystemExit(1)

    print(
        "SUCCESS: JD analyzer unit tests passed."
    )


if __name__ == "__main__":
    main()