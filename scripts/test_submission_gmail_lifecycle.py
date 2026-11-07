from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from app.applications import tracker as tracker_module
from scripts.test_email_integration import (
    GmailIntegrationTests,
    _FakeGmailService,
    _message,
)


class SubmissionToGmailLifecycleTests(GmailIntegrationTests):
    """One combined regression test for the human-confirmed submission flow."""

    def test_ready_confirmed_submission_flows_into_gmail_lifecycle(self) -> None:
        # Use a distinct role at the same company so the strict role-title
        # matcher must select this application rather than the fixture's
        # pre-existing Software Engineer application.
        created_response = self.client.post(
            "/api/applications",
            json={"job_id": 2},
        )
        self.assertEqual(created_response.status_code, 201, created_response.text)
        application_id = created_response.json()["id"]
        self.assertEqual(created_response.json()["status"], "saved")

        # The integration fixture's short Backend Engineer description is
        # intentionally lengthened to satisfy JobPilot's real readiness gate.
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE jobs SET description = ? WHERE id = 2",
                (
                    "Backend Engineer role responsible for designing, implementing, "
                    "testing, and maintaining scalable backend services. Work with "
                    "cross-functional engineering teams, APIs, databases, cloud "
                    "infrastructure, and production reliability practices.",
                ),
            )
            connection.commit()
        finally:
            connection.close()

        # The API requires an actual generated resume file before readiness.
        tracker_module.GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        resume_path = tracker_module.GENERATED_RESUMES_DIR / "Tailored_Backend_E2E.pdf"
        resume_path.write_bytes(b"%PDF-1.4 JobPilot test fixture")
        self.addCleanup(lambda: resume_path.unlink(missing_ok=True))

        ready_response = self.client.patch(
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
        self.assertEqual(ready_response.status_code, 200, ready_response.text)
        self.assertEqual(ready_response.json()["status"], "ready_to_apply")

        readiness = self.client.get(
            f"/api/applications/{application_id}/readiness"
        )
        self.assertEqual(readiness.status_code, 200, readiness.text)
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(readiness.json()["blockers"], [])

        # This is the exact request sent by the extension after the user
        # confirms that they submitted the employer form successfully.
        confirmed_response = self.client.patch(
            f"/api/applications/{application_id}",
            json={"status": "applied"},
        )
        self.assertEqual(confirmed_response.status_code, 200, confirmed_response.text)
        confirmed = confirmed_response.json()
        self.assertEqual(confirmed["status"], "applied")
        self.assertTrue(confirmed["applied_at"])
        applied_at = confirmed["applied_at"]

        # A post-submission recruiting email is discovered, matched to the
        # exact company + role, and queued for human review without changing
        # application status automatically.
        gmail_message = _message(
            message_id="gmail-e2e-backend-interview",
            subject="Interview invitation: Backend Engineer at ExampleCo",
            body=(
                "We would like to invite you to interview for the Backend Engineer "
                "role at ExampleCo. Please choose an available time."
            ),
        )
        fake_gmail = _FakeGmailService(gmail_message)
        with patch.object(self.email_module, "_gmail_service", return_value=fake_gmail):
            sync = self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 10})

        self.assertEqual(sync.status_code, 200, sync.text)
        self.assertEqual(sync.json()["imported"], 1)
        self.assertEqual(sync.json()["review_required"], 1)

        event_list = self.client.get("/api/email/events?review_status=pending")
        self.assertEqual(event_list.status_code, 200, event_list.text)
        self.assertEqual(event_list.json()["total"], 1)
        event = event_list.json()["items"][0]
        self.assertEqual(event["matched_application_id"], application_id)
        self.assertEqual(event["review_status"], "pending")
        self.assertEqual(event["proposed_status"], "interview")

        before_review = self.client.get(f"/api/applications/{application_id}").json()
        self.assertEqual(before_review["status"], "applied")
        self.assertEqual(before_review["applied_at"], applied_at)

        approval = self.client.post(
            f"/api/email/events/{event['id']}/review",
            json={"decision": "approve", "note": "Interview invitation confirmed."},
        )
        self.assertEqual(approval.status_code, 200, approval.text)
        self.assertEqual(approval.json()["before_status"], "applied")
        self.assertEqual(approval.json()["after_status"], "interview")
        self.assertTrue(approval.json()["application_status_changed"])

        after_review = self.client.get(f"/api/applications/{application_id}").json()
        self.assertEqual(after_review["status"], "interview")
        self.assertEqual(after_review["applied_at"], applied_at)


if __name__ == "__main__":
    suite = unittest.TestSuite(
        [SubmissionToGmailLifecycleTests("test_ready_confirmed_submission_flows_into_gmail_lifecycle")]
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
