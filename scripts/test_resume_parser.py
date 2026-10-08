from __future__ import annotations

from pathlib import Path

from app.resume.resume_parser import (
    ResumeParser,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

RESUME_CANDIDATES = [
    PROJECT_ROOT
    / "data"
    / "master_resume"
    / "AJAY_VARMA_KAMMAMPATI_RESUME(2).pdf",

    PROJECT_ROOT
    / "AJAY_VARMA_KAMMAMPATI_RESUME(2).pdf",
]


def check(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def locate_resume() -> Path | None:
    for path in RESUME_CANDIDATES:
        if path.exists():
            return path

    return None


def test_sample_resume_text() -> None:
    text = """
    AJAY VARMA KAMMAMPATI
    linkedin.com/in/ajayvarma915
    github.com/Ajayvarma915
    2100100055iot@gmail.com
    +91-6300311902
    Nalgonda, Telangana

    EDUCATION
    BTech - Internet Of Things(IOT)
    KL University
    CGPA : 9.5
    09/2021 - present
    Vijayawada, Andhra Pradesh

    TECHNICAL SKILLS
    Java, Python, Data Structures and Algorithms,
    Object Oriented Programming(OOPS).
    HTML, CSS, JavaScript, Git and GitHub,
    React.js, Tailwind CSS, Next.js.

    PROJECTS
    Crypto Tracker
    A cryptocurrency website displaying real-time data
    through an API for 100 coins using React.js.
    - Implemented Chart.js to compare data of two coins.

    User Management System
    Developed a user management system in Next.js
    for managing CRUD operations.
    - Implemented secure authentication and session management
      using Auth.js.

    Rule Based Chatbot
    Built a chatbot using Python.
    - Deployed the chatbot on Jetson Nano using NLP
      and Machine Learning concepts.

    VIRTUAL INTERNSHIP
    Octanet Services Private LTD - Web Development Intern
    01/2024 - 01/2024
    - Created a Todo list application using HTML,
      CSS, and JavaScript.

    CERTIFICATES
    AWS CP (Cloud Practitioner)
    Microsoft Azure Fundamentals (AZ900)
    Programming in Java - NPTEL

    ACHIEVEMENTS
    Solved 600+ problems in coding platforms.
    """

    parser = ResumeParser()

    result = parser.parse_text(
        text
    )

    check(
        result.contact.name
        == "AJAY VARMA KAMMAMPATI",
        "Name extraction failed.",
    )

    check(
        result.contact.email
        == "2100100055iot@gmail.com",
        "Email extraction failed.",
    )

    check(
        "6300311902"
        in result.contact.phone,
        "Phone extraction failed.",
    )

    check(
        len(result.education) >= 1,
        "Education was not extracted.",
    )

    check(
        result.education[0].degree
        == "Bachelor",
        "Degree should normalize to Bachelor.",
    )

    check(
        "Java" in result.skills,
        "Java should be extracted.",
    )

    check(
        "Python" in result.skills,
        "Python should be extracted.",
    )

    check(
        "React.js" in result.skills,
        "React.js should be extracted.",
    )

    check(
        "Next.js" in result.skills,
        "Next.js should be extracted.",
    )

    check(
        "Java" in result.programming_languages,
        "Java should be a programming language.",
    )

    check(
        "Python" in result.programming_languages,
        "Python should be a programming language.",
    )

    check(
        "React.js" in result.frameworks,
        "React.js should be a framework.",
    )

    check(
        "Git" in result.tools,
        "Git should be a tool.",
    )

    check(
        len(result.projects) >= 3,
        "At least three projects should be extracted.",
    )

    project_names = {
        project.name.lower()
        for project in result.projects
    }

    check(
        "crypto tracker" in project_names,
        "Crypto Tracker project missing.",
    )

    check(
        "user management system"
        in project_names,
        "User Management System missing.",
    )

    check(
        "rule based chatbot"
        in project_names,
        "Rule Based Chatbot missing.",
    )

    check(
        len(result.experience) >= 1,
        "Internship experience should be extracted.",
    )

    check(
        len(result.certifications) >= 2,
        "Certifications should be extracted.",
    )

    check(
        len(result.achievements) >= 1,
        "Achievements should be extracted.",
    )


def test_parse_real_pdf() -> None:
    resume_path = locate_resume()

    if resume_path is None:
        print(
            "Real resume PDF not found in the expected locations."
        )
        return

    parser = ResumeParser()

    result = parser.parse_file(
        resume_path
    )

    check(
        len(result.raw_text) > 1000,
        "PDF text extraction is unexpectedly short.",
    )

    check(
        "AJAY VARMA KAMMAMPATI"
        in result.raw_text,
        "Resume name not found in extracted PDF text.",
    )

    check(
        result.contact.email
        != "",
        "Email was not extracted from real PDF.",
    )

    check(
        len(result.skills) >= 5,
        "Too few skills extracted from real PDF.",
    )

    check(
        len(result.projects) >= 2,
        "Too few projects extracted from real PDF.",
    )

    check(
        len(result.certifications) >= 2,
        "Too few certifications extracted from real PDF.",
    )


def print_resume(
    result,
) -> None:
    print()
    print("========================================")
    print("Parsed Resume")
    print("========================================")

    print()
    print("Contact")
    print("----------------------------------------")
    print(
        f"Name     : {result.contact.name}"
    )
    print(
        f"Email    : {result.contact.email}"
    )
    print(
        f"Phone    : {result.contact.phone}"
    )
    print(
        f"LinkedIn : {result.contact.linkedin}"
    )
    print(
        f"GitHub   : {result.contact.github}"
    )
    print(
        f"Location : {result.contact.location}"
    )

    print()
    print("Skills")
    print("----------------------------------------")
    print(
        ", ".join(result.skills)
    )

    print()
    print("Programming Languages")
    print("----------------------------------------")
    print(
        ", ".join(
            result.programming_languages
        )
    )

    print()
    print("Frameworks")
    print("----------------------------------------")
    print(
        ", ".join(
            result.frameworks
        )
    )

    print()
    print("Tools")
    print("----------------------------------------")
    print(
        ", ".join(
            result.tools
        )
    )

    print()
    print("Concepts")
    print("----------------------------------------")
    print(
        ", ".join(
            result.concepts
        )
    )

    print()
    print("Education")
    print("----------------------------------------")

    for education in result.education:
        print(
            f"- {education.degree}: "
            f"{education.field_of_study} | "
            f"{education.institution} | "
            f"CGPA {education.cgpa}"
        )

    print()
    print("Projects")
    print("----------------------------------------")

    for index, project in enumerate(
        result.projects,
        start=1,
    ):
        print(
            f"{index}. {project.name}"
        )

        if project.technologies:
            print(
                "   Technologies: "
                + ", ".join(
                    project.technologies
                )
            )

        if project.description:
            print(
                f"   {project.description}"
            )

        for bullet in project.bullets:
            print(
                f"   - {bullet}"
            )

    print()
    print("Experience")
    print("----------------------------------------")

    for experience in result.experience:
        print(
            f"- {experience.role} "
            f"at {experience.company}"
        )

        if experience.start_date:
            print(
                f"  Dates: "
                f"{experience.start_date} - "
                f"{experience.end_date}"
            )

        for bullet in experience.bullets:
            print(
                f"  - {bullet}"
            )

    print()
    print("Certifications")
    print("----------------------------------------")

    for certification in result.certifications:
        print(
            f"- {certification.name}"
        )

    print()
    print("Achievements")
    print("----------------------------------------")

    for achievement in result.achievements:
        print(
            f"- {achievement}"
        )


def main() -> None:
    print("========================================")
    print("Resume Parser Unit Tests")
    print("========================================")

    tests = [
        test_sample_resume_text,
        test_parse_real_pdf,
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

    resume_path = locate_resume()

    if resume_path is not None:
        parser = ResumeParser()

        result = parser.parse_file(
            resume_path
        )

        print_resume(
            result
        )

    print()
    print(
        "SUCCESS: Resume parser tests passed."
    )


if __name__ == "__main__":
    main()