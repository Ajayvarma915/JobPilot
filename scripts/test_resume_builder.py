from __future__ import annotations

import tempfile
from pathlib import Path

from docx import Document

from app.resume.resume_builder import (
    ResumeBuildError,
    build_tailored_resume,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _record(
    eid: str,
    category: str,
    title: str,
    statement: str,
    section: str,
    text: str,
    metadata: dict | None = None,
    verified: bool = True,
) -> dict:
    return {
        "evidence_id": eid,
        "category": category,
        "title": title,
        "statement": statement,
        "source": {
            "file": "master_resume.pdf",
            "section": section,
            "text": text,
        },
        "metadata": metadata or {},
        "review": {
            "status": "verified" if verified else "needs_review",
            "user_verified": verified,
        },
    }


def _fixture() -> tuple[dict, dict]:
    items = [
        _record(
            "skill-js",
            "skill",
            "JavaScript",
            "Listed skill JavaScript",
            "skills",
            "JavaScript",
        ),
        _record(
            "skill-react",
            "skill",
            "React.js",
            "Listed skill React.js",
            "skills",
            "React.js",
        ),
        _record(
            "project-crypto",
            "project",
            "Crypto Tracker",
            (
                "A cryptocurrency site using React.js. Implemented Chart.js "
                "to compare coin price histories."
            ),
            "projects",
            (
                "Crypto Tracker\n"
                "A cryptocurrency site using React.js.\n"
                "Implemented Chart.js to compare coin price histories."
            ),
            {
                "technologies": [
                    "React.js",
                    "Chart.js",
                    "JavaScript",
                ],
                "bullets": [
                    "A cryptocurrency site using React.js.",
                    "Implemented Chart.js to compare coin price histories.",
                ],
            },
        ),
        _record(
            "project-users",
            "project",
            "User Management System",
            (
                "Developed a user management system in Next.js. "
                "Implemented authentication using Auth.js. Integrated Firebase."
            ),
            "projects",
            (
                "User Management System\n"
                "Developed a user management system in Next.js.\n"
                "Implemented authentication using Auth.js.\n"
                "Integrated Firebase."
            ),
            {
                # Deliberately stale metadata: JavaScript must not be
                # rendered as a technology of this project.
                "technologies": [
                    "Next.js",
                    "Auth.js",
                    "Firebase",
                    "JavaScript",
                ],
                "bullets": [
                    "Developed a user management system in Next.js.",
                    "Implemented authentication using Auth.js.",
                    "Integrated Firebase.",
                ],
            },
        ),
        _record(
            "experience-intern",
            "experience",
            "Web Development Intern at Octanet Services",
            (
                "Created Todo List and Amazon Clone projects using HTML, "
                "CSS, and JavaScript."
            ),
            "experience",
            (
                "Octanet Services - Web Development Intern\n"
                "Created Todo List and Amazon Clone projects using HTML, CSS, "
                "and JavaScript."
            ),
            {
                "role": "Web Development Intern",
                "company": "Octanet Services",
                "start_date": "01/2024",
                "end_date": "01/2024",
                "bullets": [
                    "Created a Todo List application using HTML, CSS, and JavaScript.",
                    "Developed an Amazon Clone using HTML, CSS, and JavaScript.",
                ],
            },
        ),
        _record(
            "education-btech",
            "education",
            "Bachelor — Internet Of Things — KL University",
            "Bachelor in Internet Of Things at KL University; CGPA 9.5.",
            "education",
            "BTech Internet Of Things; KL University; CGPA 9.5",
            {
                "degree": "Bachelor",
                "field_of_study": "Internet Of Things",
                "institution": "KL University",
                "cgpa": 9.5,
                "start_date": "09/2021",
                "end_date": "present",
                "location": "Vijayawada, Andhra Pradesh",
            },
        ),
        _record(
            "cert-react",
            "certification",
            "React(Basic) - HackerRank",
            "Certification listed: React(Basic) - HackerRank.",
            "certifications",
            "React(Basic) - HackerRank",
        ),
        _record(
            "achievement-coding",
            "achievement",
            "Achievement 1",
            "Solved 600+ coding problems.",
            "achievements",
            "Solved 600+ coding problems.",
        ),
    ]

    store = {
        "candidate": {
            "name": "SAMPLE CANDIDATE",
            "email": "sample@example.com",
            "phone": "+91-9000000000",
            "linkedin": "linkedin.com/in/sample",
            "github": "github.com/sample",
            "location": "Hyderabad, Telangana",
        },
        "source_resume": {
            "file": "master_resume.pdf",
            "sha256": "fake-test-hash",
        },
        "evidence": items,
    }

    selected = []

    for item in items:
        # Education is deliberately absent from the JD selection. The builder
        # must include it separately as a core section if verified.
        if item["category"] == "education":
            continue

        current = dict(item)
        current.update(
            {
                "score": 10,
                "reason": ["test evidence selected"],
                "matched_required_skills": [],
                "matched_preferred_skills": [],
                "user_verified": item["review"]["user_verified"],
                "eligible_for_resume": item["review"]["user_verified"],
            }
        )
        selected.append(current)

    selection = {
        "job": {
            "title": "Frontend Software Engineer",
        },
        "selected_evidence": selected,
        "safety": {
            "only_user_verified_records_selected": True,
            "unverified_records_are_suggestions_only": True,
            "generated_claims": False,
        },
    }

    return selection, store


def test_builds_ats_docx_and_audit() -> None:
    selection, store = _fixture()

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        output = root / "tailored_resume.docx"
        audit = root / "tailored_resume.audit.json"

        built = build_tailored_resume(
            selection,
            store,
            output,
            audit_path=audit,
        )

        check(
            built.exists() and built.stat().st_size > 1000,
            "DOCX wasn't created properly.",
        )
        check(audit.exists(), "Audit sidecar wasn't written.")

        doc = Document(str(output))
        paragraphs = [
            paragraph.text.strip()
            for paragraph in doc.paragraphs
            if paragraph.text.strip()
        ]
        content = "\n".join(paragraphs)

        check("SAMPLE CANDIDATE" in content, "Candidate name missing.")
        check("sample@example.com" in content, "Contact email missing.")
        check(
            "TECHNICAL SKILLS" in content,
            "Technical Skills section missing.",
        )
        check(
            "EXPERIENCE" in content and "Web Development Intern" in content,
            "Experience section missing.",
        )
        check(
            "Crypto Tracker" in content
            and "User Management System" in content,
            "Projects missing.",
        )
        check(
            "KL University" in content,
            "Verified education should be included even if the JD selector omitted it.",
        )
        check("EDUCATION" in content, "Education heading missing.")
        check(
            "React(Basic) - HackerRank" in content,
            "Certification missing.",
        )

        audit_text = audit.read_text(encoding="utf-8")
        check(
            '"included_as_core_section": true' in audit_text,
            "Audit must explain mandatory education inclusion.",
        )
        check(
            "Solved 600+ coding problems." in content,
            "Achievement missing.",
        )
        check("Angular" not in content, "Unsupported skill was added to resume.")

        # The stale project metadata must not become a new claim.
        project_index = paragraphs.index("User Management System")
        next_section_index = next(
            (
                i
                for i in range(project_index + 1, len(paragraphs))
                if paragraphs[i]
                in {
                    "EDUCATION",
                    "CERTIFICATIONS",
                    "ACHIEVEMENTS",
                }
            ),
            len(paragraphs),
        )

        project_block = "\n".join(
            paragraphs[project_index:next_section_index]
        )

        check(
            "Next.js" in project_block and "Auth.js" in project_block,
            "Project-source claims missing.",
        )
        check(
            "JavaScript" not in project_block,
            "Stale project metadata was rendered as a false claim.",
        )


def test_rejects_unverified_or_stale_selection() -> None:
    selection, store = _fixture()

    with tempfile.TemporaryDirectory() as temp_dir:
        output = Path(temp_dir) / "unsafe.docx"

        unsafe_selection = {
            **selection,
            "selected_evidence": [
                dict(item)
                for item in selection["selected_evidence"]
            ],
        }
        unsafe_selection["selected_evidence"][0]["user_verified"] = False

        try:
            build_tailored_resume(
                unsafe_selection,
                store,
                output,
            )
        except ResumeBuildError:
            pass
        else:
            raise AssertionError("Unverified selection must be rejected.")

        stale_selection = {
            **selection,
            "selected_evidence": [
                dict(item)
                for item in selection["selected_evidence"]
            ],
        }
        stale_selection["selected_evidence"][0]["statement"] = (
            "Changed since selection"
        )

        try:
            build_tailored_resume(
                stale_selection,
                store,
                output,
            )
        except ResumeBuildError:
            pass
        else:
            raise AssertionError("Stale selection must be rejected.")


def main() -> int:
    tests = [
        (
            "ATS DOCX generation, evidence-only content, and audit sidecar",
            test_builds_ats_docx_and_audit,
        ),
        (
            "Rejects unverified and stale selection reports",
            test_rejects_unverified_or_stale_selection,
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 68)
    print("Tailored Resume Builder Tests")
    print("=" * 68)

    for number, (name, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {number}: PASS - {name}")
        except Exception as exc:
            failed += 1
            print(
                f"Test {number}: FAIL - {name}\n"
                f"  {type(exc).__name__}: {exc}"
            )

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: Tailored resume builder tests failed.")
        return 1

    print("SUCCESS: Tailored resume builder tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())