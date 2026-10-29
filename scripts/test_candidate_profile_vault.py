from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


MASTER_RESUME_TEXT = """Ajay Varma Kammampati
ajay.varma@example.com | +91 90000 11111 | Hyderabad, India
https://www.linkedin.com/in/ajay-varma | https://github.com/ajayvarma

TECHNICAL SKILLS
Python, JavaScript, React.js, FastAPI, SQL

EXPERIENCE
Systems Engineer — Tata Consultancy Services
September 2025 - Present
- Works on software engineering and application development tasks.

EDUCATION
Bachelor of Technology in Internet of Things — KL University
2021 - Present

PROJECTS
JobPilot Application Assistant
- Built a local job discovery and application preparation workflow using FastAPI and React.

CERTIFICATIONS
Microsoft Azure Fundamentals (AZ-900)

ACHIEVEMENTS
Solved programming problems on online coding platforms.
"""


class CandidateProfileVaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="jobpilot_profile_vault_")
        root = Path(cls.temp_dir.name)
        cls.database_path = root / "jobpilot_test.db"
        os.environ["JOBPILOT_DATABASE_PATH"] = str(cls.database_path)

        connection = sqlite3.connect(cls.database_path)
        connection.executescript(
            """
            PRAGMA foreign_keys=ON;
            CREATE TABLE companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                location TEXT,
                url TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );
            INSERT INTO companies(name) VALUES ('ExampleCo');
            INSERT INTO jobs(company_id,title,location,url,description,source,is_active)
            VALUES
              (1,'Software Engineer','Hyderabad, India','https://example.com/job/1',
               'A detailed software engineering role requiring skills and experience. ' ||
               'Responsibilities include developing, testing, and maintaining applications.',
               'greenhouse',1),
              (1,'Backend Engineer','Bengaluru, India','https://example.com/job/2',
               'A detailed backend engineering role requiring skills and experience. ' ||
               'Responsibilities include API development, testing, and maintenance.',
               'greenhouse',1);
            """
        )
        connection.commit()
        connection.close()

        import app.applications.tracker as tracker_module
        cls.tracker_module = tracker_module
        cls.original_resume_dir = tracker_module.MASTER_RESUME_DIRECTORY
        cls.original_generated_dir = tracker_module.GENERATED_RESUMES_DIR
        tracker_module.MASTER_RESUME_DIRECTORY = root / "master_resumes"
        tracker_module.MASTER_RESUME_DIRECTORY.mkdir(parents=True, exist_ok=True)
        tracker_module.GENERATED_RESUMES_DIR = root / "generated_resumes"
        tracker_module.GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)

        cls.app = FastAPI()
        cls.app.include_router(tracker_module.router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.tracker_module.MASTER_RESUME_DIRECTORY = cls.original_resume_dir
        cls.tracker_module.GENERATED_RESUMES_DIR = cls.original_generated_dir
        cls.temp_dir.cleanup()
        os.environ.pop("JOBPILOT_DATABASE_PATH", None)

    def setUp(self) -> None:
        self.client.get("/api/applications/stats")
        connection = sqlite3.connect(self.database_path)
        connection.execute("DELETE FROM application_preparations")
        connection.execute("DELETE FROM candidate_profile_vault")
        connection.execute("DELETE FROM applications")
        connection.execute("UPDATE jobs SET is_active = 1")
        connection.commit()
        connection.close()
        for file in self.tracker_module.MASTER_RESUME_DIRECTORY.iterdir():
            if file.is_file():
                file.unlink()

    def create_application(self, job_id: int = 1) -> int:
        response = self.client.post("/api/applications", json={"job_id": job_id})
        self.assertEqual(response.status_code, 201, response.text)
        return int(response.json()["id"])

    def test_profile_saved_once_prefills_a_new_application(self) -> None:
        first_id = self.create_application(1)
        response = self.client.patch(
            f"/api/applications/{first_id}/preparation",
            json={
                "contact_name": "Ajay Varma Kammampati",
                "email": "ajay@example.com",
                "phone": "+91 90000 11111",
                "current_location": "Hyderabad, India",
                "linkedin_url": "https://www.linkedin.com/in/ajay-varma",
                "github_url": "https://github.com/ajayvarma",
                "current_employer": "Tata Consultancy Services",
                "current_title": "Systems Engineer",
                "years_experience": "1 year",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)

        profile = self.client.get("/api/applications/candidate-profile")
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["profile"]["contact_name"], "Ajay Varma Kammampati")
        self.assertEqual(profile.json()["profile"]["email"], "ajay@example.com")
        self.assertEqual(profile.json()["profile_source"], "application_preparation")

        second_id = self.create_application(2)
        new_preparation = self.client.get(f"/api/applications/{second_id}/preparation")
        self.assertEqual(new_preparation.status_code, 200, new_preparation.text)
        saved_profile = new_preparation.json()["profile"]
        self.assertEqual(saved_profile["contact_name"], "Ajay Varma Kammampati")
        self.assertEqual(saved_profile["email"], "ajay@example.com")
        self.assertEqual(saved_profile["current_employer"], "Tata Consultancy Services")

    def test_global_profile_edit_syncs_only_changed_fields(self) -> None:
        first_id = self.create_application(1)
        self.client.patch(
            f"/api/applications/{first_id}/preparation",
            json={
                "contact_name": "Ajay Varma",
                "email": "old@example.com",
                "phone": "+91 90000 11111",
                "current_location": "Hyderabad, India",
            },
        )
        second_id = self.create_application(2)
        self.client.get(f"/api/applications/{second_id}/preparation")

        updated = self.client.patch(
            "/api/applications/candidate-profile",
            json={"email": "new@example.com"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["profile"]["email"], "new@example.com")

        first = self.client.get(f"/api/applications/{first_id}/preparation").json()
        second = self.client.get(f"/api/applications/{second_id}/preparation").json()
        self.assertEqual(first["profile"]["email"], "new@example.com")
        self.assertEqual(second["profile"]["email"], "new@example.com")
        self.assertEqual(second["profile"]["contact_name"], "Ajay Varma")

    def test_master_resume_import_parses_contact_and_resume_facts(self) -> None:
        resume = self.tracker_module.MASTER_RESUME_DIRECTORY / "master_resume.txt"
        resume.write_text(MASTER_RESUME_TEXT, encoding="utf-8")

        imported = self.client.post(
            "/api/applications/candidate-profile/import-master-resume",
            json={"filename": "master_resume.txt", "overwrite": True},
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        body = imported.json()
        self.assertEqual(body["profile"]["contact_name"], "Ajay Varma Kammampati")
        self.assertEqual(body["profile"]["email"], "ajay.varma@example.com")
        self.assertEqual(body["profile"]["current_location"], "Hyderabad, India")
        self.assertEqual(body["source_resume_filename"], "master_resume.txt")
        self.assertEqual(body["profile_source"], "master_resume")
        self.assertIn("Python", body["resume_facts"]["skills"])
        self.assertTrue(body["resume_facts"]["projects"])
        self.assertTrue(body["resume_facts"]["experience"])
        self.assertNotIn("raw_text", body["resume_facts"])

    def test_import_does_not_overwrite_confirmed_manual_contact_by_default(self) -> None:
        profile = self.client.patch(
            "/api/applications/candidate-profile",
            json={
                "contact_name": "Manually Confirmed Name",
                "email": "confirmed@example.com",
            },
        )
        self.assertEqual(profile.status_code, 200, profile.text)

        resume = self.tracker_module.MASTER_RESUME_DIRECTORY / "master_resume.txt"
        resume.write_text(MASTER_RESUME_TEXT, encoding="utf-8")
        imported = self.client.post(
            "/api/applications/candidate-profile/import-master-resume",
            json={"filename": "master_resume.txt", "overwrite": False},
        )
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["profile"]["contact_name"], "Manually Confirmed Name")
        self.assertEqual(imported.json()["profile"]["email"], "confirmed@example.com")
        self.assertTrue(imported.json()["resume_facts"]["skills"])

    def test_import_requires_explicit_file_when_master_folder_is_ambiguous(self) -> None:
        (self.tracker_module.MASTER_RESUME_DIRECTORY / "resume1.txt").write_text(
            MASTER_RESUME_TEXT, encoding="utf-8"
        )
        (self.tracker_module.MASTER_RESUME_DIRECTORY / "resume2.md").write_text(
            MASTER_RESUME_TEXT, encoding="utf-8"
        )
        response = self.client.post(
            "/api/applications/candidate-profile/import-master-resume",
            json={"overwrite": True},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            set(response.json()["detail"]["available_files"]),
            {"resume1.txt", "resume2.md"},
        )

    def test_invalid_global_email_and_url_are_rejected(self) -> None:
        invalid_email = self.client.patch(
            "/api/applications/candidate-profile",
            json={"email": "not-an-email"},
        )
        self.assertEqual(invalid_email.status_code, 422)

        invalid_url = self.client.patch(
            "/api/applications/candidate-profile",
            json={"github_url": "javascript:alert(1)"},
        )
        self.assertEqual(invalid_url.status_code, 422)

    def test_profile_endpoint_reports_required_fields_without_faking_completion(self) -> None:
        response = self.client.get("/api/applications/candidate-profile")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["complete"])
        self.assertEqual(
            set(response.json()["missing_required"]),
            {"contact_name", "email", "phone", "current_location"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
