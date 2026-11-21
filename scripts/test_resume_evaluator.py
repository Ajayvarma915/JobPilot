from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.resume.resume_builder import build_tailored_resume
from app.resume.resume_evaluator import _style_checks, evaluate_generated_resume
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


class WritingStyleTests(unittest.TestCase):
    @staticmethod
    def _selection(bullets):
        return {"selected_evidence": [{"category": "experience", "metadata": {"bullets": bullets}}]}

    def test_clean_resume_scores_high(self) -> None:
        style = _style_checks(self._selection([
            "Built a queue worker that cut batch failures by 40% across 12 services.",
            "Migrated authentication from SASL to OAuth 2.0 in 3 Node.js services.",
            "Wrote 850+ unit tests across 11 repositories to meet an 85% coverage gate.",
            "Designed an approval loop with 11 stages and a circuit breaker after 5 failures.",
        ]))
        self.assertGreaterEqual(style["score"], 95, style)
        self.assertEqual((style["repeated_openers"], style["similar_pairs"], style["repeated_phrases"]), ([], 0, []))
        self.assertEqual(style["metric_share"], 1.0)

    def test_repetition_is_found_and_explained(self) -> None:
        style = _style_checks(self._selection([
            "Built a dashboard for the support team with charts and filters for tickets.",
            "Built a dashboard for the support team with charts and filters for tickets.",
            "Built an export tool that writes reports every night for managers.",
            "Built a notification service that emails managers when a report is ready.",
        ]))
        self.assertEqual(style["repeated_openers"], [{"word": "built", "count": 4}])
        self.assertGreaterEqual(style["similar_pairs"], 1)
        self.assertTrue(style["repeated_phrases"])
        self.assertLess(style["score"], 60, style)
        joined = " ".join(style["issues"])
        self.assertIn("start with", joined)
        self.assertIn("almost the same thing", joined)

    def test_missing_numbers_are_flagged_without_inventing_any(self) -> None:
        style = _style_checks(self._selection([
            "Created a scheduling tool for the team using React and Node.js.",
            "Improved the onboarding flow for new users with clearer steps.",
            "Developed an internal wiki that helps engineers find answers faster.",
        ]))
        self.assertEqual(style["metric_share"], 0.0)
        self.assertTrue(any("never invents metrics" in issue for issue in style["issues"]))

    def test_overall_score_and_the_85_target_are_reported(self) -> None:
        selection, store = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docx_path, pdf_path = root / "t.docx", root / "t.pdf"
            build_tailored_resume(selection, store, docx_path)
            build_tailored_resume_pdf(selection, store, pdf_path)
            result = evaluate_generated_resume(docx_path, pdf_path, selection, store)
        overall = result["overall"]
        self.assertEqual(overall["target"], 85)
        self.assertEqual(overall["meets_target"], overall["score"] >= 85)
        parts = (result["ats_readability"]["score"], result["job_relevance"]["score"], result["achievement_quality"]["score"], result["writing_style"]["score"])
        self.assertEqual(overall["score"], round(0.25 * parts[0] + 0.40 * parts[1] + 0.20 * parts[2] + 0.15 * parts[3]))
        if not overall["meets_target"]:
            self.assertTrue(overall["to_reach_target"], "a score below the target must say what to do")
            self.assertTrue(any("SQL" in line for line in overall["to_reach_target"]), "the missing required skill is named")
        self.assertFalse(result["readiness_passes_local_checks"], "a missing required skill still blocks readiness")


if __name__ == "__main__":
    unittest.main(verbosity=2)
