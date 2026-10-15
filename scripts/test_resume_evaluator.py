from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.resume.resume_builder import build_tailored_resume
from app.resume.resume_evaluator import evaluate_generated_resume
from app.resume.resume_pdf_builder import build_tailored_resume_pdf


def _evidence(
    evidence_id: str,
    category: str,
    title: str,
    statement: str,
    *,
    metadata: dict | None = None,
    required: list[str] | None = None,
    preferred: list[str] | None = None,
    technologies: list[str] | None = None,
) -> dict:
    source = {"file": "master_resume.docx", "section": category, "text": statement}
    return {
        "evidence_id": evidence_id,
        "category": category,
        "title": title,
        "statement": statement,
        "source": source,
        "metadata": metadata or {},
        "review": {"user_verified": True, "status": "verified"},
        "matched_required_skills": required or [],
        "matched_preferred_skills": preferred or [],
        "matched_job_technologies": technologies or [],
    }


def fixture() -> tuple[dict, dict]:
    evidence = [
        _evidence("skill-python", "skill", "Python", "Listed as a skill in the source resume.", required=["Python"]),
        _evidence("skill-react", "skill", "React.js", "Listed as a skill in the source resume.", required=["React.js"], preferred=["React.js"]),
        _evidence(
            "exp-1", "experience", "Web Development Intern",
            "Created a Todo list application using HTML, CSS, and JavaScript, supporting users managing tasks.",
            metadata={
                "role": "Web Development Intern", "company": "Example Company",
                "start_date": "2024-01", "end_date": "2024-03",
                "bullets": [
                    "Developed a Todo list application using HTML, CSS, and JavaScript, supporting task creation, editing, completion, and deletion.",
                    "Implemented task state handling and responsive layouts to make common task workflows easier to use.",
                ],
                "technologies": ["HTML", "CSS", "JavaScript"],
            }, technologies=["JavaScript"],
        ),
        _evidence(
            "project-1", "project", "Rule Based Chatbot",
            "Built a Python chatbot that accepts text and voice inputs and delivers text and voice outputs.",
            metadata={"bullets": [
                "Built a Python chatbot supporting text and voice input and output, and deployed it on Jetson Nano.",
                "Integrated Google Search functionality using PyWhatKit to support responses to user queries.",
            ], "technologies": ["Python", "NLP"]}, required=["Python"], technologies=["Python"],
        ),
        _evidence(
            "education-1", "education", "Bachelor of Technology",
            "Bachelor of Technology in Computer Science, Example University.",
            metadata={"degree": "Bachelor of Technology", "field_of_study": "Computer Science", "institution": "Example University", "start_date": "2021", "end_date": "2025"},
        ),
    ]
    store = {
        "candidate": {
            "name": "Sample Candidate",
            "email": "candidate@example.com",
            "phone": "+91 90000 00000",
            "location": "Hyderabad, Telangana",
            "linkedin": "linkedin.com/in/sample-candidate",
            "github": "github.com/sample-candidate",
        },
        "source_resume": {"file": "master_resume.docx", "sha256": "fixture"},
        "evidence": evidence,
    }
    # Selection records deliberately reuse the current store's exact source and statement so
    # that the builder's stale-evidence protection is exercised.
    selected = []
    for item in evidence:
        if item["category"] in {"skill", "experience", "project"}:
            selected_item = dict(item)
            selected_item["score"] = 10
            selected_item["reason"] = ["matches the job description"]
            selected_item["user_verified"] = True
            selected.append(selected_item)
    selection = {
        "job": {"title": "Junior Software Engineer"},
        "signals": {
            "required_skills": ["Python", "React.js", "SQL"],
            "preferred_skills": ["React.js", "Docker"],
            "inferred_job_technologies": ["Python", "JavaScript", "SQL"],
        },
        "coverage": {
            "required_skills": 3,
            "verified_covered": ["Python", "React.js"],
            "awaiting_evidence_review": [],
            "not_found_in_evidence": ["SQL"],
        },
        "selected_evidence": selected,
        "review_queue": [],
        "safety": {
            "only_user_verified_records_selected": True,
            "unverified_records_are_suggestions_only": True,
            "generated_claims": False,
        },
    }
    return selection, store


class ResumeEvaluatorTests(unittest.TestCase):
    def test_generates_parseable_docx_and_pdf_with_separate_scores(self) -> None:
        selection, store = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_path = root / "tailored.docx"
            pdf_path = root / "tailored.pdf"
            build_tailored_resume(selection, store, docx_path)
            build_tailored_resume_pdf(selection, store, pdf_path)
            result = evaluate_generated_resume(docx_path, pdf_path, selection, store)

            self.assertTrue(docx_path.is_file())
            self.assertTrue(pdf_path.is_file())
            self.assertGreater(result["ats_readability"]["score"], 0)
            self.assertGreater(result["job_relevance"]["score"], 0)
            self.assertGreater(result["achievement_quality"]["score"], 0)
            self.assertEqual(result["job_relevance"]["required_skill_coverage"]["missing"], ["SQL"])
            self.assertIn("not official", result["global_disclaimer"].lower())

    def test_ats_score_is_not_presented_as_employer_score(self) -> None:
        selection, store = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_path = root / "tailored.docx"
            pdf_path = root / "tailored.pdf"
            build_tailored_resume(selection, store, docx_path)
            build_tailored_resume_pdf(selection, store, pdf_path)
            result = evaluate_generated_resume(docx_path, pdf_path, selection, store)
            self.assertIn("not a score assigned", result["ats_readability"]["disclaimer"].lower())
            self.assertIsInstance(result["readiness_passes_local_checks"], bool)

    def test_missing_required_skill_remains_visible_even_with_good_formatting(self) -> None:
        selection, store = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_path = root / "tailored.docx"
            pdf_path = root / "tailored.pdf"
            build_tailored_resume(selection, store, docx_path)
            build_tailored_resume_pdf(selection, store, pdf_path)
            result = evaluate_generated_resume(docx_path, pdf_path, selection, store)
            self.assertIn("SQL", result["job_relevance"]["required_skill_coverage"]["missing"])
            self.assertFalse(result["readiness_passes_local_checks"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
