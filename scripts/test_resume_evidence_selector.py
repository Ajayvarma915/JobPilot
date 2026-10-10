from __future__ import annotations

import tempfile
from pathlib import Path

from app.resume.evidence_selector import ResumeEvidenceSelector
from app.resume.evidence_store import MasterResumeEvidenceStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_RESUME = """
SAMPLE CANDIDATE
sample@example.com
EDUCATION
BTech - Computer Science
Example University
CGPA: 8.8
2021 - 2025
TECHNICAL SKILLS
Java, Python, JavaScript, React.js, HTML, CSS, Git, Data Structures and Algorithms
PROJECTS
Inventory Dashboard
Built an inventory dashboard using React.js, JavaScript, HTML, and CSS.
• Added charts, search, and responsive UI features.
User Management System
Developed a user management system using Next.js, Auth.js, and Firebase.
• Implemented credentials authentication and session management.
Rule-Based Chatbot
Built a chatbot using Python and Natural Language Processing.
• Accepted text input and returned responses.
CERTIFICATIONS
Python - Example Academy
ACHIEVEMENTS
• Solved 100 coding challenges.
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _build_test_store(root: Path) -> tuple[MasterResumeEvidenceStore, dict]:
    source = root / "sample_resume.txt"
    source.write_text(SAMPLE_RESUME, encoding="utf-8")
    store = MasterResumeEvidenceStore(root / "evidence.json")
    data = store.build_from_file(source)
    return store, data


def test_selector_separates_verified_from_unverified() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        store, data = _build_test_store(root)

        result = ResumeEvidenceSelector(store.store_path).select_for_job(
            job_title="Frontend Software Engineer",
            job_description=(
                "Build responsive web interfaces using React.js and JavaScript. "
                "Work with HTML and CSS to implement accessible UI components."
            ),
            required_skills=["ReactJS", "JavaScript"],
            preferred_skills=["HTML", "CSS"],
        )

        check(
            result["counts"]["verified_selected"] == 0,
            "Unverified records entered selected evidence.",
        )
        check(
            result["review_queue"],
            "Relevant unverified evidence should be suggested for review.",
        )
        check(
            all(not item["eligible_for_resume"] for item in result["review_queue"]),
            "Review queue items must not be resume-eligible.",
        )
        check(
            set(result["coverage"]["awaiting_evidence_review"])
            == {"React.js", "JavaScript"},
            f"Unexpected review coverage: {result['coverage']}",
        )

        skill_matches = {
            item["title"]: set(item["matched_required_skills"])
            for item in result["review_queue"]
            if item["category"] == "skill"
        }

        check(
            skill_matches.get("React.js") == {"React.js"},
            "React.js skill record incorrectly matched neighboring skills: "
            f"{skill_matches.get('React.js')}",
        )
        check(
            skill_matches.get("JavaScript") == {"JavaScript"},
            "JavaScript skill record incorrectly matched neighboring skills: "
            f"{skill_matches.get('JavaScript')}",
        )
        check(
            "Tailwind CSS" not in skill_matches,
            "A partial word overlap must not count Tailwind CSS as direct CSS evidence.",
        )
        check(
            result["safety"]["generated_claims"] is False,
            "Selector must not create claims.",
        )

        skill_by_title = {
            item["title"]: item
            for item in data["evidence"]
            if item["category"] == "skill"
        }

        project = next(
            item
            for item in data["evidence"]
            if item["category"] == "project"
            and item["title"] == "Inventory Dashboard"
        )

        store.set_verified(
            skill_by_title["React.js"]["evidence_id"],
            True,
            note="Checked against source resume",
        )
        store.set_verified(
            skill_by_title["JavaScript"]["evidence_id"],
            True,
            note="Checked against source resume",
        )
        store.set_verified(
            project["evidence_id"],
            True,
            note="Checked project details against source resume",
        )

        verified_result = ResumeEvidenceSelector(store.store_path).select_for_job(
            job_title="Frontend Software Engineer",
            job_description=(
                "Build responsive web interfaces using React.js and JavaScript. "
                "Work with HTML and CSS to implement accessible UI components."
            ),
            required_skills=["ReactJS", "JavaScript", "Angular"],
            preferred_skills=["HTML", "CSS"],
        )

        selected_ids = {
            item["evidence_id"]
            for item in verified_result["selected_evidence"]
        }

        check(
            project["evidence_id"] in selected_ids,
            "Relevant verified project not selected.",
        )
        check(
            all(item["user_verified"] for item in verified_result["selected_evidence"]),
            "An unverified record was selected.",
        )
        check(
            verified_result["coverage"]["verified_covered"]
            == ["React.js", "JavaScript"],
            f"Verified required coverage is wrong: {verified_result['coverage']}",
        )
        check(
            "Angular" in verified_result["coverage"]["not_found_in_evidence"],
            "Missing Angular requirement must not be fabricated.",
        )


def test_js_suffix_is_not_misclassified_as_javascript() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        store, data = _build_test_store(root)

        project = next(
            item
            for item in data["evidence"]
            if item["category"] == "project"
            and item["title"] == "User Management System"
        )

        selector = ResumeEvidenceSelector(store.store_path)

        result = selector.select_for_job(
            job_title="Full Stack Engineer",
            job_description=(
                "Maintain a user management application built with "
                "Next.js, Auth.js, and Firebase."
            ),
            required_skills=["JavaScript"],
            preferred_skills=["Next.js", "Auth.js", "Firebase"],
        )

        selected_project = next(
            item
            for item in result["review_queue"]
            if item["evidence_id"] == project["evidence_id"]
        )

        check(
            "JavaScript" not in selected_project["matched_required_skills"],
            "Next.js/Auth.js must not imply JavaScript skill evidence.",
        )

        inferred_result = selector.select_for_job(
            job_title="Full Stack Engineer",
            job_description="Maintain an application built with Next.js and Auth.js.",
        )

        inferred = {
            item.casefold()
            for item in inferred_result["signals"]["inferred_job_technologies"]
        }

        check(
            "javascript" not in inferred,
            f"`.js` suffix was incorrectly inferred as JavaScript: {inferred}",
        )


def test_selector_handles_real_evidence_store() -> None:
    store_path = (
        PROJECT_ROOT
        / "data"
        / "master_resume"
        / "master_resume_evidence.json"
    )

    if not store_path.exists():
        raise FileNotFoundError(
            "Master resume evidence JSON not found at "
            "data/master_resume/master_resume_evidence.json"
        )

    result = ResumeEvidenceSelector(store_path).select_for_job(
        job_title="Frontend Software Engineer",
        job_description=(
            "Build frontend applications with JavaScript, React.js, "
            "Next.js, HTML, and CSS. Create accessible interfaces "
            "and maintain responsive web applications."
        ),
        required_skills=["JavaScript", "React.js"],
        preferred_skills=["Next.js", "HTML", "CSS"],
    )

    check(
        result["review_queue"] or result["selected_evidence"],
        "Real resume should produce relevant evidence for this JD.",
    )
    check(
        all(item["user_verified"] is True for item in result["selected_evidence"]),
        "Selected evidence must be user-verified.",
    )
    check(
        all(item["user_verified"] is False for item in result["review_queue"]),
        "Review queue must contain only unverified evidence.",
    )
    check(
        result["safety"]["only_user_verified_records_selected"] is True,
        "Selector safety metadata should preserve the verification gate.",
    )


def main() -> int:
    tests = [
        (
            "Verified-only selection, review queue, coverage, no invented requirements",
            test_selector_separates_verified_from_unverified,
        ),
        (
            ".js suffix is not misclassified as JavaScript",
            test_js_suffix_is_not_misclassified_as_javascript,
        ),
        (
            "Real resume evidence respects verification status",
            test_selector_handles_real_evidence_store,
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 68)
    print("Resume Evidence Selector Tests")
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
        print("FAILURE: Resume Evidence Selector tests failed.")
        return 1

    print("SUCCESS: Resume Evidence Selector tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())