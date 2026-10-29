from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


class ApplicationTrackerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(
            prefix="jobpilot_applications_"
        )
        cls.database_path = Path(cls.temp_dir.name) / "test_jobpilot.db"

        os.environ["JOBPILOT_DATABASE_PATH"] = str(cls.database_path)

        connection = sqlite3.connect(cls.database_path)

        import app.applications.tracker as tracker_module
        cls.tracker_module = tracker_module
        cls.original_generated_resumes_dir = tracker_module.GENERATED_RESUMES_DIR
        cls.original_master_resume_directory = tracker_module.MASTER_RESUME_DIRECTORY
        tracker_module.GENERATED_RESUMES_DIR = Path(cls.temp_dir.name) / "generated_resumes"
        tracker_module.GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        tracker_module.MASTER_RESUME_DIRECTORY = Path(cls.temp_dir.name) / "master_resumes"
        tracker_module.MASTER_RESUME_DIRECTORY.mkdir(parents=True, exist_ok=True)

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

            INSERT INTO companies (name)
            VALUES ('ExampleCo');

            INSERT INTO jobs (
                company_id, title, location, url, description, source, is_active
            )
            VALUES (
                1,
                'Software Engineer',
                'Hyderabad, India',
                'https://example.com/jobs/1',
                'Minimum qualifications include a bachelor degree and experience. ' ||
                'Review responsibilities, technical requirements, application steps, and qualifications.',
                'greenhouse',
                1
            );

            INSERT INTO jobs (
                company_id, title, location, url, description, source, is_active
            )
            VALUES (
                1,
                'Backend Engineer',
                'Remote',
                'https://example.com/jobs/2',
                'Minimum qualifications include a bachelor degree and experience. ' ||
                'Review responsibilities, technical requirements, application steps, and qualifications.',
                'greenhouse',
                1
            );
            """
        )

        connection.commit()
        connection.close()

        from app.applications.tracker import router

        cls.app = FastAPI()
        cls.app.include_router(router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.temp_dir.cleanup()
        os.environ.pop("JOBPILOT_DATABASE_PATH", None)
        cls.tracker_module.GENERATED_RESUMES_DIR = cls.original_generated_resumes_dir
        cls.tracker_module.MASTER_RESUME_DIRECTORY = cls.original_master_resume_directory

    def setUp(self) -> None:
        # Initialize the table through the API before clearing test data.
        self.client.get("/api/applications/stats")

        connection = sqlite3.connect(self.database_path)
        connection.execute("DELETE FROM application_preparations")
        connection.execute("DELETE FROM candidate_profile_vault")
        connection.execute("DELETE FROM applications")
        connection.execute("UPDATE jobs SET is_active = 1")
        connection.commit()
        connection.close()

    def test_empty_list_and_stats(self) -> None:
        response = self.client.get("/api/applications")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["items"], [])

        stats = self.client.get("/api/applications/stats")

        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total"], 0)
        self.assertIn(
            "ready_to_apply",
            stats.json()["by_status"],
        )

    def test_create_deduplicate_and_search(self) -> None:
        response = self.client.post(
            "/api/applications",
            json={
                "job_id": 1,
                "notes": "Review role and tailor resume",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)

        created = response.json()

        self.assertEqual(created["status"], "saved")
        self.assertEqual(created["job"]["company"], "ExampleCo")
        self.assertEqual(created["job"]["title"], "Software Engineer")

        duplicate = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )

        self.assertEqual(duplicate.status_code, 409)

        search = self.client.get(
            "/api/applications",
            params={"q": "ExampleCo"},
        )

        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["total"], 1)

    def test_status_transition_follow_up_and_stats(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 2},
        ).json()

        response = self.client.patch(
            f"/api/applications/{created['id']}",
            json={
                "status": "applied",
                "notes": "Application submitted manually",
                "next_action": "Check confirmation email",
                "follow_up_date": "2026-10-23",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)

        updated = response.json()

        self.assertEqual(updated["status"], "applied")
        self.assertIsNotNone(updated["applied_at"])
        self.assertEqual(updated["follow_up_date"], "2026-10-23")

        stats = self.client.get("/api/applications/stats").json()

        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["by_status"]["applied"], 1)

        filtered = self.client.get(
            "/api/applications",
            params={"status": "saved"},
        ).json()

        self.assertEqual(filtered["total"], 0)

    def test_tracked_job_ids_and_by_job_lookup(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )
        self.assertEqual(created.status_code, 201, created.text)

        ids = self.client.get("/api/applications/tracked-job-ids")
        self.assertEqual(ids.status_code, 200)
        self.assertEqual(ids.json()["job_ids"], [1])

        by_job = self.client.get("/api/applications/by-job/1")
        self.assertEqual(by_job.status_code, 200, by_job.text)
        self.assertEqual(by_job.json()["id"], created.json()["id"])

    def test_remove_tracker_entry_keeps_original_job(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 1, "notes": "Accidentally tracked"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        removed = self.client.delete(f"/api/applications/{application_id}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json(), {
            "deleted": True,
            "application_id": application_id,
            "job_id": 1,
        })

        listing = self.client.get("/api/applications")
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()["total"], 0)

        ids = self.client.get("/api/applications/tracked-job-ids")
        self.assertEqual(ids.json()["job_ids"], [])

        connection = sqlite3.connect(self.database_path)
        try:
            job = connection.execute(
                "SELECT title FROM jobs WHERE id = 1"
            ).fetchone()
            self.assertEqual(job[0], "Software Engineer")
        finally:
            connection.close()

        # The same job can be tracked again after removal.
        retracked = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )
        self.assertEqual(retracked.status_code, 201, retracked.text)

    def test_delete_missing_application_returns_404(self) -> None:
        response = self.client.delete("/api/applications/987")
        self.assertEqual(response.status_code, 404)

    def test_readiness_blocks_until_required_review_is_complete(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        readiness = self.client.get(
            f"/api/applications/{application_id}/readiness"
        )
        self.assertEqual(readiness.status_code, 200, readiness.text)
        payload = readiness.json()
        self.assertFalse(payload["ready"])
        self.assertIn("Generated tailored resume selected", payload["blockers"])
        self.assertGreaterEqual(payload["total_checks"], 8)
        self.assertEqual(payload["job"]["title"], "Software Engineer")

        blocked = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "ready_to_apply"},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn("blockers", blocked.json()["detail"])

    def test_ready_status_requires_resume_and_all_confirmations(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        resume_path = self.tracker_module.GENERATED_RESUMES_DIR / "Tailored_Test.pdf"
        resume_path.write_bytes(b"%PDF-1.4 test fixture")

        update = self.client.patch(
            f"/api/applications/{application_id}",
            json={
                "status": "ready_to_apply",
                "resume_filename": resume_path.name,
                "job_reviewed": True,
                "eligibility_confirmed": True,
                "resume_reviewed": True,
                "application_details_reviewed": True,
            },
        )
        self.assertEqual(update.status_code, 200, update.text)
        self.assertEqual(update.json()["status"], "ready_to_apply")
        self.assertTrue(update.json()["job_reviewed"])
        self.assertEqual(update.json()["resume_filename"], resume_path.name)

        readiness = self.client.get(
            f"/api/applications/{application_id}/readiness"
        )
        self.assertEqual(readiness.status_code, 200, readiness.text)
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(readiness.json()["blockers"], [])

    def test_inactive_job_cannot_be_marked_ready(self) -> None:
        created = self.client.post(
            "/api/applications",
            json={"job_id": 1},
        )
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        connection = sqlite3.connect(self.database_path)
        connection.execute("UPDATE jobs SET is_active = 0 WHERE id = 1")
        connection.commit()
        connection.close()

        resume_path = self.tracker_module.GENERATED_RESUMES_DIR / "InactiveRole.pdf"
        resume_path.write_bytes(b"%PDF-1.4 test fixture")

        blocked = self.client.patch(
            f"/api/applications/{application_id}",
            json={
                "status": "ready_to_apply",
                "resume_filename": resume_path.name,
                "job_reviewed": True,
                "eligibility_confirmed": True,
                "resume_reviewed": True,
                "application_details_reviewed": True,
            },
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertTrue(
            any("marked active" in value for value in blocked.json()["detail"]["blockers"])
        )

    def test_application_preparation_starts_incomplete(self) -> None:
        created = self.client.post("/api/applications", json={"job_id": 1})
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        response = self.client.get(
            f"/api/applications/{application_id}/preparation"
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertFalse(payload["prepared"])
        self.assertIn("Add your full name.", payload["blockers"])
        self.assertEqual(payload["job"]["company"], "ExampleCo")
        self.assertEqual(payload["custom_questions"], [])

    def test_application_preparation_saves_profile_and_custom_answers(self) -> None:
        created = self.client.post("/api/applications", json={"job_id": 1})
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        resume_path = self.tracker_module.GENERATED_RESUMES_DIR / "Prepared_Resume.pdf"
        resume_path.write_bytes(b"%PDF-1.4 test fixture")

        response = self.client.patch(
            f"/api/applications/{application_id}/preparation",
            json={
                "contact_name": "Test Candidate",
                "email": "candidate@example.com",
                "phone": "+91 90000 00000",
                "current_location": "Hyderabad, India",
                "linkedin_url": "https://www.linkedin.com/in/test-candidate",
                "github_url": "https://github.com/test-candidate",
                "current_employer": "Example Employer",
                "current_title": "Systems Engineer",
                "years_experience": "1 year",
                "notice_period": "30 days",
                "work_authorization": "Authorized to work in India",
                "requires_sponsorship": "no",
                "salary_expectation": "As per company policy",
                "resume_filename": resume_path.name,
                "cover_letter_draft": "Dear hiring team, I am applying for this role.",
                "custom_questions": [
                    {
                        "question": "Why are you interested in this role?",
                        "answer": "The role aligns with my verified software engineering skills.",
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["prepared"], payload["blockers"])
        self.assertEqual(payload["profile"]["contact_name"], "Test Candidate")
        self.assertEqual(payload["resume_filename"], resume_path.name)
        self.assertEqual(len(payload["custom_questions"]), 1)
        self.assertTrue(payload["prepared_at"])

        fetched = self.client.get(
            f"/api/applications/{application_id}/preparation"
        )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["profile"]["email"], "candidate@example.com")
        self.assertEqual(
            fetched.json()["custom_questions"][0]["answer"],
            "The role aligns with my verified software engineering skills.",
        )

    def test_application_preparation_validates_email_and_profile_urls(self) -> None:
        created = self.client.post("/api/applications", json={"job_id": 1})
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        invalid_email = self.client.patch(
            f"/api/applications/{application_id}/preparation",
            json={"email": "not-an-email"},
        )
        self.assertEqual(invalid_email.status_code, 422)

        invalid_url = self.client.patch(
            f"/api/applications/{application_id}/preparation",
            json={"linkedin_url": "javascript:alert(1)"},
        )
        self.assertEqual(invalid_url.status_code, 422)

    def test_unanswered_custom_question_blocks_preparation(self) -> None:
        created = self.client.post("/api/applications", json={"job_id": 1})
        self.assertEqual(created.status_code, 201, created.text)
        application_id = created.json()["id"]

        response = self.client.patch(
            f"/api/applications/{application_id}/preparation",
            json={
                "contact_name": "Test Candidate",
                "email": "candidate@example.com",
                "phone": "+91 90000 00000",
                "current_location": "Hyderabad, India",
                "custom_questions": [
                    {"question": "Are you willing to relocate?", "answer": ""}
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["prepared"])
        self.assertTrue(
            any("custom employer question 1" in item for item in response.json()["blockers"])
        )

    def test_invalid_job_and_status_are_rejected(self) -> None:
        missing_job = self.client.post(
            "/api/applications",
            json={"job_id": 999},
        )

        self.assertEqual(missing_job.status_code, 404)

        invalid_status = self.client.post(
            "/api/applications",
            json={
                "job_id": 1,
                "status": "magically_hired",
            },
        )

        self.assertEqual(invalid_status.status_code, 422)

        missing_application = self.client.patch(
            "/api/applications/987",
            json={"status": "interview"},
        )

        self.assertEqual(missing_application.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)