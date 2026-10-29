from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path


class CandidateProfileMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(
            prefix="jobpilot_match_profile_"
        )
        cls.database_path = Path(cls.temp_dir.name) / "match_profile.db"

        os.environ["JOBPILOT_DATABASE_PATH"] = str(cls.database_path)

        # Import after setting the path so the API module uses the isolated DB.
        from app.api import main

        cls.main = main
        cls.original_database_path = main.DATABASE_PATH
        main.DATABASE_PATH = cls.database_path

        connection = sqlite3.connect(cls.database_path)
        try:
            connection.execute(
                """
                CREATE TABLE candidate_profile_vault (
                    id INTEGER PRIMARY KEY,
                    resume_facts_json TEXT
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    @classmethod
    def tearDownClass(cls) -> None:
        # Dispose SQLAlchemy's connection pool before deleting the temporary DB.
        try:
            cls.main.engine.dispose(close=True)
        finally:
            cls.main.DATABASE_PATH = cls.original_database_path
            os.environ.pop("JOBPILOT_DATABASE_PATH", None)
            cls.temp_dir.cleanup()

    def setUp(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("DELETE FROM candidate_profile_vault")
            connection.commit()
        finally:
            connection.close()

    def test_static_profile_is_used_before_resume_import(self) -> None:
        profile = self.main._candidate_profile()

        self.assertIn("Python", profile.technical_skills)
        self.assertGreaterEqual(profile.years_of_experience, 1.0)

    def test_imported_resume_facts_update_job_matching_profile(self) -> None:
        facts = {
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "programming_languages": ["Python"],
            "frameworks": ["FastAPI"],
            "tools": ["PostgreSQL"],
            "concepts": ["REST APIs"],
            "education": [
                {
                    "degree": "Bachelor of Technology",
                    "field_of_study": "Computer Science",
                    "institution": "Example University",
                }
            ],
            "projects": [
                {
                    "name": "API Platform",
                    "technologies": ["FastAPI", "PostgreSQL"],
                }
            ],
            "experience": [],
            "certifications": [{"name": "Cloud Fundamentals"}],
            "achievements": [],
        }

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO candidate_profile_vault (
                    id, resume_facts_json
                ) VALUES (1, ?)
                """,
                (json.dumps(facts),),
            )
            connection.commit()
        finally:
            connection.close()

        profile = self.main._candidate_profile()

        self.assertEqual(
            profile.technical_skills,
            ("Python", "FastAPI", "PostgreSQL"),
        )
        self.assertEqual(profile.frameworks, ("FastAPI",))
        self.assertEqual(profile.tools, ("PostgreSQL",))
        self.assertEqual(
            profile.project_skills,
            ("FastAPI", "PostgreSQL"),
        )
        self.assertEqual(
            profile.certifications,
            ("Cloud Fundamentals",),
        )
        self.assertEqual(
            profile.education,
            (
                "Bachelor of Technology — Computer Science — "
                "Example University",
            ),
        )

    def test_malformed_profile_facts_fall_back_without_crashing(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO candidate_profile_vault (
                    id, resume_facts_json
                ) VALUES (1, ?)
                """,
                ("{broken",),
            )
            connection.commit()
        finally:
            connection.close()

        profile = self.main._candidate_profile()

        self.assertIn("Python", profile.technical_skills)
        self.assertIsInstance(profile.technical_skills, tuple)


if __name__ == "__main__":
    unittest.main(verbosity=2)