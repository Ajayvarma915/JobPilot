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
                source TEXT NOT NULL,
                FOREIGN KEY(company_id) REFERENCES companies(id)
            );

            INSERT INTO companies (name)
            VALUES ('ExampleCo');

            INSERT INTO jobs (
                company_id, title, location, url, source
            )
            VALUES (
                1,
                'Software Engineer',
                'Hyderabad, India',
                'https://example.com/jobs/1',
                'greenhouse'
            );

            INSERT INTO jobs (
                company_id, title, location, url, source
            )
            VALUES (
                1,
                'Backend Engineer',
                'Remote',
                'https://example.com/jobs/2',
                'greenhouse'
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

    def setUp(self) -> None:
        # Initialize the table through the API before clearing test data.
        self.client.get("/api/applications/stats")

        connection = sqlite3.connect(self.database_path)
        connection.execute("DELETE FROM applications")
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

        removed = self.client.delete(
            f"/api/applications/{application_id}"
        )
        self.assertEqual(removed.status_code, 200, removed.text)

        self.assertEqual(
            removed.json(),
            {
                "deleted": True,
                "application_id": application_id,
                "job_id": 1,
            },
        )

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