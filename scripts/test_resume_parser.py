from __future__ import annotations

from pathlib import Path

from app.resume.resume_parser import ResumeParser, parse_resume_file

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_RESUME_TEXT = """
AJAY VARMA KAMMAMPATI
linkedin.com/in/ajayvarma915
github.com/Ajayvarma915
2100100055iot@gmail.com
+91-6300311902
Nalgonda,Telangana
EDUCATION
BTech-Internet Of Things(IOT)
KL University
CGPA : 9.5
09/2021 – present
Vijayawada,
Andhra Pradesh
TECHNICAL SKILLS
LANGUAGES/TOOLS/FRAMEWORKS/CONCEPTS
•Java, Python, Data Structures and Algorithms, Object Oriented Programming(OOPS).
•HTML, CSS, JavaScript, Git and GitHub, React.js, Tailwind CSS, Next.js.
PROJECTS
Crypto Tracker
A cryptocurrency website displaying real-time data through an API for 100 coins using React.js.
•I implemented Chart.js to compare data of two coins, showing price history over the last 24 hours.
•Achieving a 90% score for performance and 93% for accessibility in Lighthouse Tool.
User Management System
Developed a user management system in Next.js for managing CRUD operations of over 100+ users.
•Implemented secure authentication, session management using Auth.js for credentials login.
3. •Integrated Firebase as the database for efficient and scalable data storage.
Rule Based Chatbot
Built a chatbot using Python that accepts both text, voice inputs and delivers text, voice outputs.
•Deployed the chatbot on Jetson Nano, leveraging NLP techniques and Machine Learning concepts.
•Attained 80% response accuracy and integrated Google search functionality using PyWhatKit.
VIRTUAL INTERNSHIP
Octanet Services Private LTD - Web Development Intern
Project 1: Todo List Application
01/2024 – 01/2024
•Created a Todo list application using HTML, CSS, and JavaScript, enabling
functionalities for adding, deleting, updating, editing, and marking tasks as
completed, with support for managing up to 50 tasks.
Project 2: Amazon Clone
•Developed a fully functional Amazon clone website using HTML, CSS, and
JavaScript. Showcasing expertise in front-end web development. through
product listings, sidebar navigations, Image sliders.
CERTIFICATES
AWS CP (Cloud Practitioner)
Python - HackerRank
Microsoft Azure
Fundamentals (AZ900)
React(Basic) - HackerRank
Java - HackerRank
Programming in Java - NPTEL
ACHIEVEMENTS
•Achieved a Global Rank of 189, 681, 910 in codechef Starters 82, 80, 83.
•Solved 600+ problems in coding platforms like Leetcode, Codeforces, codechef, GeeksforGeeks and
HackerRank combined.
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_sample_resume_text() -> None:
    resume = ResumeParser().parse_text(SAMPLE_RESUME_TEXT)

    check(resume.contact.name == "AJAY VARMA KAMMAMPATI", f"Name: {resume.contact.name!r}")
    check(resume.contact.email == "2100100055iot@gmail.com", "Email was not extracted.")
    check(
        resume.contact.phone is not None and "6300311902" in resume.contact.phone,
        f"Phone: {resume.contact.phone!r}",
    )
    check(resume.contact.linkedin == "linkedin.com/in/ajayvarma915", "LinkedIn was not extracted.")
    check(resume.contact.github == "github.com/Ajayvarma915", "GitHub was not extracted.")
    check(resume.contact.location == "Nalgonda, Telangana", f"Location: {resume.contact.location!r}")

    check(resume.education and resume.education[0].degree == "Bachelor", "Education degree was not parsed.")
    education = resume.education[0]
    check(education.institution == "KL University" and education.cgpa == 9.5, "Education details were not parsed.")
    check(
        education.field_of_study and "Internet Of Things" in education.field_of_study,
        "Field of study was not parsed.",
    )

    expected_skills = {
        "Java", "Python", "JavaScript", "HTML", "CSS", "React.js",
        "Tailwind CSS", "Next.js", "Git", "GitHub",
        "Data Structures and Algorithms", "Object-Oriented Programming",
    }
    check(
        expected_skills.issubset(set(resume.skills)),
        f"Missing skills: {sorted(expected_skills - set(resume.skills))}",
    )
    check(
        {"Java", "Python"}.issubset(resume.programming_languages),
        "Programming language categories are wrong.",
    )
    check(
        {"React.js", "Next.js"}.issubset(resume.frameworks),
        "Framework categories are wrong.",
    )

    project_names = [project.name for project in resume.projects]
    check(
        project_names == ["Crypto Tracker", "User Management System", "Rule Based Chatbot"],
        f"Project titles: {project_names!r}",
    )
    check("Firebase" in resume.projects[1].technologies, "Firebase should belong to User Management System.")
    check(
        any("Integrated Firebase" in bullet for bullet in resume.projects[1].bullets),
        "Firebase bullet was lost.",
    )
    check(
        not any("Integrated Firebase" in name for name in project_names),
        "A project bullet was misclassified as a title.",
    )
    check("Chart.js" in resume.projects[0].technologies, "Chart.js should belong to Crypto Tracker.")
    check("PyWhatKit" in resume.projects[2].technologies, "PyWhatKit should belong to Rule Based Chatbot.")

    check(len(resume.experience) == 1, f"Internship count: {len(resume.experience)}")
    internship = resume.experience[0]
    check(internship.company == "Octanet Services Private LTD", f"Company: {internship.company!r}")
    check(internship.role == "Web Development Intern", f"Role: {internship.role!r}")
    check(
        (internship.start_date, internship.end_date) == ("01/2024", "01/2024"),
        "Internship dates were not parsed.",
    )
    check(
        any("Todo List Application" in item for item in internship.bullets),
        "Todo List project detail was lost.",
    )
    check(
        any("Amazon Clone" in item for item in internship.bullets),
        "Amazon Clone detail was lost.",
    )

    certs = [item.name for item in resume.certifications]
    check("Microsoft Azure Fundamentals (AZ900)" in certs, f"Azure certification split: {certs!r}")
    check(
        len(certs) == 6 and "Fundamentals (AZ900)" not in certs,
        f"Certification grouping: {certs!r}",
    )
    check(len(resume.achievements) == 2, f"Achievement grouping: {resume.achievements!r}")
    check(
        "HackerRank combined." in resume.achievements[-1],
        "Wrapped achievement continuation was lost.",
    )


def test_real_resume_pdf() -> None:
    candidates = [
        PROJECT_ROOT / "data/master_resume/AJAY_VARMA_KAMMAMPATI_RESUME(2).pdf",
        PROJECT_ROOT / "AJAY_VARMA_KAMMAMPATI_RESUME(2).pdf",
    ]
    pdf = next((path for path in candidates if path.exists()), None)

    if pdf is None:
        raise FileNotFoundError(
            "Place your PDF at data/master_resume/"
            "AJAY_VARMA_KAMMAMPATI_RESUME(2).pdf before running this test."
        )

    resume = parse_resume_file(pdf)
    check(len(resume.raw_text) > 1000, "Extracted PDF text is too short.")
    check(resume.contact.name == "AJAY VARMA KAMMAMPATI", f"PDF name: {resume.contact.name!r}")
    check(resume.contact.email == "2100100055iot@gmail.com", "PDF email was not extracted.")
    check(len(resume.skills) >= 10, f"Too few PDF skills: {resume.skills!r}")

    names = [project.name for project in resume.projects]
    check(
        names == ["Crypto Tracker", "User Management System", "Rule Based Chatbot"],
        f"PDF project titles: {names!r}",
    )
    check(
        "Firebase" in resume.projects[1].technologies,
        "PDF Firebase bullet is attached to the wrong project.",
    )

    certs = [item.name for item in resume.certifications]
    check("Microsoft Azure Fundamentals (AZ900)" in certs, f"PDF Azure certification split: {certs!r}")
    check(
        len(resume.achievements) == 2
        and "HackerRank combined." in resume.achievements[-1],
        f"PDF achievements: {resume.achievements!r}",
    )
    check(
        resume.experience and resume.experience[0].role == "Web Development Intern",
        "PDF internship role was not extracted.",
    )


def main() -> int:
    print("=" * 40, "\nResume Parser Regression Tests\n", "=" * 40, sep="")
    tests = [
        ("Synthetic resume and regression cases", test_sample_resume_text),
        ("Real resume PDF regression cases", test_real_resume_pdf),
    ]
    passed = failed = 0

    for number, (name, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {number}: PASS - {name}")
        except Exception as exc:
            failed += 1
            print(f"Test {number}: FAIL - {name}\n  {type(exc).__name__}: {exc}")

    print(f"\nUnit tests: {passed} passed, {failed} failed")
    if failed:
        print("FAILURE: Resume parser regression tests failed.")
        return 1

    print("SUCCESS: Resume parser regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())