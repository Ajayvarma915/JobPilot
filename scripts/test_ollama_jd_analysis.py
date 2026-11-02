from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.ai.jd_insights import (
    JD_INSIGHTS_SCHEMA,
    _validate_insights,
    analyze_job_description_with_ollama,
)
from app.ai.ollama_client import OllamaResponseError, generate_structured, get_status


class JDInsightsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.description = """
        Minimum qualifications
        Bachelor's degree in Computer Science.
        2+ years of software development experience.
        Experience with Python, Java, and SQL.
        Build backend services and REST APIs.

        Preferred qualifications
        Experience with AWS and React.js is a plus.
        """
        self.valid_payload = {
            "role_summary": "Build backend services and APIs.",
            "role_family": "backend",
            "seniority": "entry",
            "minimum_experience_years": 2,
            "required_skills": ["Python", "Java", "SQL", "Kubernetes"],
            "preferred_skills": ["AWS", "React.js", "Terraform"],
            "key_responsibilities": ["Build backend services and REST APIs"],
            "required_qualifications": ["Bachelor's degree in Computer Science"],
            "preferred_qualifications": ["Cloud experience is a plus"],
            "uncertainties": [],
        }

    @patch("app.ai.jd_insights.generate_structured")
    def test_analysis_uses_local_structured_output_and_filters_unsupported_skills(self, mocked_generate):
        mocked_generate.return_value = json.dumps(self.valid_payload)
        result = analyze_job_description_with_ollama(
            title="Backend Software Engineer",
            description=self.description,
            location="Hyderabad",
            required_years_evidence=2.0,
        )
        self.assertEqual(result["insights"]["required_skills"], ["Python", "Java", "SQL"])
        self.assertEqual(result["insights"]["preferred_skills"], ["AWS", "React.js"])
        self.assertEqual(result["insights"]["minimum_experience_years"], 2.0)
        self.assertFalse(result["input_truncated"])
        mocked_generate.assert_called_once()
        self.assertEqual(mocked_generate.call_args.args[1], JD_INSIGHTS_SCHEMA)

    def test_unsubstantiated_qualification_is_filtered(self):
        payload = dict(self.valid_payload)
        payload["required_qualifications"] = [
            "Bachelor's degree in Computer Science",
            "Ten years of Kubernetes administration",
        ]
        validated = _validate_insights(
            json.dumps(payload),
            source_text=self.description,
            required_years_evidence=2.0,
        )
        self.assertEqual(
            validated["required_qualifications"],
            ["Bachelor's degree in Computer Science"],
        )

    def test_experience_is_removed_when_deterministic_baseline_has_no_required_years(self):
        payload = dict(self.valid_payload)
        validated = _validate_insights(
            json.dumps(payload),
            source_text=self.description,
            required_years_evidence=None,
        )
        self.assertIsNone(validated["minimum_experience_years"])

    def test_invalid_model_json_is_rejected(self):
        with self.assertRaises(OllamaResponseError):
            _validate_insights("not json", source_text=self.description)

    @patch("app.ai.jd_insights.generate_structured")
    def test_short_description_does_not_call_ollama(self, mocked_generate):
        with self.assertRaises(ValueError):
            analyze_job_description_with_ollama(title="Engineer", description="Too short")
        mocked_generate.assert_not_called()

    @patch("app.ai.jd_insights.generate_structured")
    def test_long_description_is_bounded(self, mocked_generate):
        payload = dict(self.valid_payload)
        mocked_generate.return_value = json.dumps(payload)
        long_description = "Python backend development. " * 2000
        result = analyze_job_description_with_ollama(
            title="Backend Engineer",
            description=long_description,
            required_years_evidence=None,
        )
        self.assertTrue(result["input_truncated"])
        self.assertLessEqual(result["source_characters"], 30_000)


class OllamaClientTests(unittest.TestCase):
    @patch("app.ai.ollama_client.OLLAMA_MODEL", "gemma3:4b")
    @patch("app.ai.ollama_client.list_models")
    def test_status_requires_exact_model_tag(self, mocked_models):
        mocked_models.return_value = ["gemma3:1b"]
        result = get_status()
        self.assertTrue(result["available"])
        self.assertFalse(result["model_installed"])

    @patch("app.ai.ollama_client.requests.post")
    def test_structured_generation_sends_json_schema(self, mocked_post):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"response": '{"ok": true}'}

        mocked_post.return_value = FakeResponse()
        result = generate_structured("Return JSON", {"type": "object"}, model="gemma3:4b")
        self.assertEqual(result, '{"ok": true}')
        kwargs = mocked_post.call_args.kwargs
        self.assertEqual(kwargs["json"]["format"], {"type": "object"})
        self.assertEqual(kwargs["json"]["model"], "gemma3:4b")
        self.assertFalse(kwargs["json"]["stream"])

    @patch("app.ai.ollama_client.list_models")
    def test_status_reports_configured_model(self, mocked_models):
        mocked_models.return_value = ["gemma3:4b", "qwen2.5:7b"]
        result = get_status()
        self.assertTrue(result["available"])
        self.assertTrue(result["model_installed"])
        self.assertIn("gemma3:4b", result["installed_models"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
