from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.resume.evidence_store import MasterResumeEvidenceStore
from app.resume.resume_parser import ResumeParser

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_TEXT = """
SAMPLE CANDIDATE
sample@example.com
EDUCATION
BTech - Computer Science
Example University
CGPA: 8.8
2021 - 2025
TECHNICAL SKILLS
Java, Python, React.js, Git, Data Structures and Algorithms
PROJECTS
Inventory Dashboard
Built an inventory dashboard using React.js and JavaScript.
• Added charts and search.
EXPERIENCE
Example Company - Software Developer Intern
01/2024 - 06/2024
• Created internal tools using Python.
CERTIFICATIONS
Python - Example Academy
ACHIEVEMENTS
• Solved 100 coding challenges.
"""


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_build_store_from_parsed_text() -> None:
    parsed = ResumeParser().parse_text(SAMPLE_TEXT)

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = root / "sample_resume.txt"
        source.write_text(SAMPLE_TEXT, encoding="utf-8")

        store_path = root / "evidence.json"
        store = MasterResumeEvidenceStore(store_path)
        data = store.build_from_parsed(parsed, source_path=source)

        check(data["schema_version"] == 1, "Unexpected schema version.")
        check(
            data["candidate"]["name"] == "SAMPLE CANDIDATE",
            "Candidate name missing.",
        )
        check(data["evidence_count"] > 0, "No evidence records were created.")

        expected_categories = {
            "skill",
            "education",
            "project",
            "experience",
            "certification",
            "achievement",
        }

        check(
            expected_categories.issubset(set(data["counts_by_category"])),
            f"Evidence categories missing: {data['counts_by_category']}",
        )
        check(store_path.exists(), "JSON evidence store was not written.")

        # Independently confirm it is valid JSON and traceable.
        decoded = json.loads(store_path.read_text(encoding="utf-8"))
        check(
            decoded["source_resume"]["file"] == "sample_resume.txt",
            "Source filename missing.",
        )

        for item in data["evidence"]:
            check(item["evidence_id"], "Evidence ID missing.")
            check(
                item["source"]["file"] == "sample_resume.txt",
                "Source file missing on evidence.",
            )
            check(
                item["source"]["section"],
                f"Source section missing: {item['title']}",
            )
            check(
                item["source"]["text"],
                f"Source text missing: {item['title']}",
            )
            check(
                item["review"]["user_verified"] is False,
                "New evidence must not be pre-verified.",
            )
            check(
                item["review"]["status"] == "needs_review",
                "New evidence must need review.",
            )

        project = next(
            item
            for item in data["evidence"]
            if item["category"] == "project"
        )

        store.set_verified(
            project["evidence_id"],
            True,
            note="Manually checked.",
        )

        verified = next(
            item
            for item in store.load()["evidence"]
            if item["evidence_id"] == project["evidence_id"]
        )

        check(
            verified["review"]["user_verified"] is True,
            "Explicit verification was not saved.",
        )
        check(
            verified["review"]["note"] == "Manually checked.",
            "Review note was not saved.",
        )

        # Rebuilding identical source evidence preserves explicit verification.
        rebuilt = store.build_from_parsed(parsed, source_path=source)

        rebuilt_project = next(
            item
            for item in rebuilt["evidence"]
            if item["evidence_id"] == project["evidence_id"]
        )

        check(
            rebuilt_project["review"]["user_verified"] is True,
            "Verification was not preserved.",
        )

        unverified = store.list_evidence(user_verified=False)
        check(
            unverified,
            "Unverified evidence filter unexpectedly returned no records.",
        )

        search_results = store.list_evidence(query="Inventory Dashboard")
        check(
            search_results,
            "Evidence search did not find the project.",
        )


def _find_real_resume() -> Path:
    """The one resume PDF in data/master_resume (whatever it is called), so the test follows your latest resume."""
    folder = PROJECT_ROOT / "data" / "master_resume"
    pdfs = sorted(folder.glob("*.pdf")) if folder.exists() else []
    if len(pdfs) != 1:
        raise FileNotFoundError(f"Keep exactly one resume PDF in data/master_resume (found {len(pdfs)}).")
    return pdfs[0]


def test_real_resume_pdf_store() -> None:
    resume_path = _find_real_resume()
    with tempfile.TemporaryDirectory() as temp_dir:
        store = MasterResumeEvidenceStore(Path(temp_dir) / "real_resume_evidence.json")
        data = store.build_from_file(resume_path)
        check(bool(data["source_resume"]["sha256"]), "Resume fingerprint missing.")
        check(len(data["candidate"]["name"] or "") > 3, "Candidate name missing from store.")
        counts = data["counts_by_category"]
        for category in ("skill", "project", "experience", "education"):
            check(counts.get(category, 0) >= 1, f"No {category} evidence was built: {counts!r}")
        check(data["evidence_count"] == len(data["evidence"]), "Evidence count is inconsistent.")
        check(all(not item["review"]["user_verified"] for item in data["evidence"]), "A new store must start with nothing verified.")
        check(all(item["source"].get("text") or item.get("statement") for item in data["evidence"]), "A record has no source text.")


def main() -> int:
    tests = [
        (
            "Synthetic evidence creation, traceability, review, and search",
            test_build_store_from_parsed_text,
        ),
        (
            "Real resume PDF evidence extraction",
            test_real_resume_pdf_store,
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 52)
    print("Master Resume Evidence Store Tests")
    print("=" * 52)

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
        print("FAILURE: Master Resume Evidence Store tests failed.")
        return 1

    print("SUCCESS: Master Resume Evidence Store tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())