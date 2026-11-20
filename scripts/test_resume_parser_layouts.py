"""Resume parser tests for the layout many modern resumes use (a made-up resume, not anyone's real one).

Layout: "Role | Company | MM/YYYY - Present" headers, bullets that lost their markers and wrap over
several lines, "Name | subtitle" project headings followed by a technologies line, "Label: a, b, c"
skills, and several certifications on one line.
"""
from __future__ import annotations

from app.resume.resume_parser import ResumeParser

SAMPLE = """JANE EXAMPLE
Pune, India | +91-9000000000 | jane@example.com
linkedin.com/in/janeexample | github.com/janeexample
SUMMARY
Backend engineer.
EXPERIENCE
Software Engineer | Acme Systems | 03/2025 - Present
Client: a retail bank
Reduced batch failures by moving the retry logic into a queue worker, adding idempotency keys and
a dead-letter topic for rejected records (2,000+ records per run).
Wrote 300+ unit tests across 6 services to meet the 80% coverage gate.
PROJECTS
Shop API | Orders and payments REST API
Node.js, Express, MongoDB, JWT | github.com/janeexample/shop-api
Built a 20-endpoint REST API with role-based access control enforced in middleware.
Added JWT refresh tokens with email verification.
Chat Tool | Realtime support chat
Python, FastAPI, Redis | github.com/janeexample/chat
Created a websocket gateway that fans messages out through Redis streams to connected agents
across several workers.
TECHNICAL SKILLS
Languages: Java, Python, TypeScript
Backend and Cloud: Node.js, Apache Kafka (KafkaJS), OAuth 2.0, Docker, CI/CD (Azure
Pipelines), Redis
Testing: Jest, SonarQube
EDUCATION
B.Tech, Computer Science | Example University, Pune, Maharashtra | CGPA: 8.9 | 08/2021 - 05/2025
CERTIFICATIONS
AWS Certified Cloud Practitioner | Microsoft Azure Fundamentals (AZ-900)
ACHIEVEMENTS
Ranked 120 in a national coding contest.
500+ problems solved across coding platforms.
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_pipe_headers_and_unmarked_bullets() -> None:
    resume = ResumeParser().parse_text(SAMPLE)
    check(len(resume.experience) == 1, f"one job: {resume.experience}")
    job = resume.experience[0]
    check((job.role, job.company, job.start_date, job.end_date) == ("Software Engineer", "Acme Systems", "03/2025", "Present"), job)
    check(len(job.bullets) == 2, f"two bullets, wrapped lines joined: {job.bullets}")
    check(job.bullets[0].endswith("(2,000+ records per run).") and "dead-letter topic" in job.bullets[0], job.bullets[0])
    check(not any("Client:" in bullet for bullet in job.bullets), "the client line is not evidence")


def test_projects_with_pipe_titles() -> None:
    resume = ResumeParser().parse_text(SAMPLE)
    check([p.name for p in resume.projects] == ["Shop API | Orders and payments REST API", "Chat Tool | Realtime support chat"], resume.projects)
    shop, chat = resume.projects
    check(len(shop.bullets) == 2 and len(chat.bullets) == 1, (shop.bullets, chat.bullets))
    check({"Node.js", "MongoDB", "JWT"} <= set(shop.technologies) and {"Python", "FastAPI", "Redis"} <= set(chat.technologies),
          (shop.technologies, chat.technologies))
    check(chat.bullets[0].endswith("across several workers."), chat.bullets[0])


def test_listed_skills_certifications_education_and_achievements() -> None:
    resume = ResumeParser().parse_text(SAMPLE)
    skills = set(resume.skills)
    check({"Java", "Python", "TypeScript", "Node.js", "Kafka", "OAuth 2.0", "Redis", "Jest", "SonarQube"} <= skills, sorted(skills))
    check(any(s.startswith("CI/CD") and s.endswith("Pipelines)") for s in skills), "a wrapped skill line is joined")
    check([c.name for c in resume.certifications] == ["AWS Certified Cloud Practitioner", "Microsoft Azure Fundamentals (AZ-900)"],
          resume.certifications)
    edu = resume.education[0]
    check((edu.degree, edu.field_of_study, edu.institution, edu.cgpa, edu.start_date, edu.end_date) ==
          ("B.Tech", "Computer Science", "Example University", 8.9, "08/2021", "05/2025"), edu)
    check(len(resume.achievements) == 2 and resume.achievements[1].startswith("500+"), resume.achievements)


def test_older_layout_still_parses() -> None:
    old = "\n".join([
        "JOHN OLD", "Hyderabad, India | john@example.com", "EXPERIENCE", "Acme Corp - Web Development Intern", "01/2024 - 03/2024",
        "• Built a todo list application using HTML, CSS and JavaScript.", "PROJECTS", "Crypto Tracker",
        "• A cryptocurrency website displaying live prices using React.js.", "• Added Chart.js to compare two coins.",
        "SKILLS", "Languages: Java, Python", "CERTIFICATIONS", "Python - HackerRank", "ACHIEVEMENTS", "• Solved 600+ problems.",
    ])
    resume = ResumeParser().parse_text(old)
    check(len(resume.experience) == 1 and resume.experience[0].company == "Acme Corp" and len(resume.experience[0].bullets) == 1, resume.experience)
    check(len(resume.projects) == 1 and resume.projects[0].name == "Crypto Tracker" and len(resume.projects[0].bullets) == 2, resume.projects)
    check([c.name for c in resume.certifications] == ["Python - HackerRank"], resume.certifications)


TESTS = [
    ("Pipe headers and unmarked wrapped bullets", test_pipe_headers_and_unmarked_bullets),
    ("Projects with Name | subtitle headings and a technologies line", test_projects_with_pipe_titles),
    ("Listed skills, certifications, education and achievements", test_listed_skills_certifications_education_and_achievements),
    ("The older resume layout still parses", test_older_layout_still_parses),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
