from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRequest:
    def __init__(self, result: dict) -> None:
        self.result = result

    def execute(self) -> dict:
        return self.result


class _FakeMessages:
    def __init__(self, message: dict) -> None:
        self.message = message

    def list(self, **kwargs):
        return _FakeRequest({"messages": [{"id": self.message["id"], "threadId": self.message["threadId"]}]})

    def get(self, **kwargs):
        return _FakeRequest(self.message)


class _FakeUsers:
    def __init__(self, message: dict) -> None:
        self._messages = _FakeMessages(message)

    def messages(self):
        return self._messages


class _FakeGmailService:
    def __init__(self, message: dict) -> None:
        self._users = _FakeUsers(message)

    def users(self):
        return self._users


class _PagedFakeMessages:
    def __init__(self, messages_by_id: dict[str, dict], pages: dict) -> None:
        self.messages_by_id = messages_by_id
        self.pages = pages
        self.list_calls: list[dict] = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        page_token = kwargs.get("pageToken")
        return _FakeRequest(self.pages.get(page_token, {"messages": []}))

    def get(self, **kwargs):
        return _FakeRequest(self.messages_by_id[kwargs["id"]])


class _PagedFakeUsers:
    def __init__(self, messages: dict[str, dict], pages: dict) -> None:
        self._messages = _PagedFakeMessages(messages, pages)

    def messages(self):
        return self._messages


class _PagedFakeGmailService:
    def __init__(self, messages: dict[str, dict], pages: dict) -> None:
        self._users = _PagedFakeUsers(messages, pages)

    def users(self):
        return self._users


def _message(*, message_id: str = "gmail-message-1", subject: str | None = None, body: str | None = None) -> dict:
    subject = subject or "Interview invitation: Software Engineer at ExampleCo"
    body = body or "We would like to invite you to interview for the Software Engineer role at ExampleCo."
    encoded_body = base64.urlsafe_b64encode(body.encode("utf-8")).decode("ascii").rstrip("=")
    return {
        "id": message_id,
        "threadId": "gmail-thread-1",
        "internalDate": str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        "snippet": body[:200],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "ExampleCo Recruiting <recruiting@exampleco.com>"},
                {"name": "Subject", "value": subject},
            ],
            "body": {"data": encoded_body},
        },
    }


class GmailIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="jobpilot_email_test_")
        root = Path(cls.temp_dir.name)
        cls.database_path = root / "email_test.db"
        cls.token_path = root / "tokens" / "gmail_token.json"
        cls.client_secrets_path = root / "missing_google_client.json"
        os.environ["JOBPILOT_DATABASE_PATH"] = str(cls.database_path)
        os.environ["JOBPILOT_GMAIL_TOKEN_PATH"] = str(cls.token_path)
        os.environ["JOBPILOT_GOOGLE_CLIENT_SECRETS"] = str(cls.client_secrets_path)

        connection = sqlite3.connect(cls.database_path)
        try:
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
                INSERT INTO jobs(company_id, title, location, url, description, source, is_active)
                VALUES (1, 'Software Engineer', 'Hyderabad, India',
                        'https://exampleco.com/careers/software-engineer',
                        'A full software engineering position with interview stages.', 'greenhouse', 1);
                INSERT INTO jobs(company_id, title, location, url, description, source, is_active)
                VALUES (1, 'Backend Engineer', 'Hyderabad, India',
                        'https://exampleco.com/careers/backend-engineer',
                        'A backend engineering position with interview stages.', 'greenhouse', 1);
                """
            )
            connection.commit()
        finally:
            connection.close()

        from app.applications.tracker import router as applications_router
        from app.email.gmail_integration import router as email_router

        cls.email_module = __import__("app.email.gmail_integration", fromlist=["router"])
        cls.app = FastAPI()
        cls.app.include_router(applications_router)
        cls.app.include_router(email_router)
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        os.environ.pop("JOBPILOT_DATABASE_PATH", None)
        os.environ.pop("JOBPILOT_GMAIL_TOKEN_PATH", None)
        os.environ.pop("JOBPILOT_GOOGLE_CLIENT_SECRETS", None)
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        self.client.get("/api/email/status")
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("DELETE FROM application_email_events")
            connection.execute("DELETE FROM email_scanned_messages")
            connection.execute("DELETE FROM applications")
            connection.execute("DELETE FROM email_oauth_states")
            connection.execute("DELETE FROM email_sync_state")
            connection.commit()
        finally:
            connection.close()
        # Gmail may only update applications that the user has explicitly
        # marked as submitted in JobPilot.
        self.application = self.client.post(
            "/api/applications", json={"job_id": 1, "status": "applied"}
        ).json()

    def test_classifier_detects_core_events(self) -> None:
        classify = self.email_module.classify_email
        cases = [
            ("Thank you for applying", "Thank you for applying to ExampleCo.", "application_confirmation", "applied"),
            ("Online assessment invitation", "Please complete the online assessment for your ExampleCo application.", "assessment_invitation", "assessment"),
            ("Interview invitation", "We would like to invite you to interview for the Software Engineer role.", "interview_invitation", "interview"),
            ("Offer letter", "We are pleased to offer you the position.", "offer", "offer"),
            ("Application update", "We are not moving forward with your application.", "rejection", "rejected"),
        ]
        for subject, body, expected_type, expected_status in cases:
            with self.subTest(subject=subject):
                result = classify(subject=subject, body_text=body)
                self.assertIsNotNone(result)
                self.assertEqual(result["event_type"], expected_type)
                self.assertEqual(result["proposed_status"], expected_status)

    def test_unrelated_email_is_not_classified(self) -> None:
        result = self.email_module.classify_email(
            subject="Your monthly account statement",
            body_text="Your account statement is now available.",
        )
        self.assertIsNone(result)

    def test_job_ads_newsletters_and_college_notifications_are_not_lifecycle_events(self) -> None:
        classify = self.email_module.classify_email
        # Regression fixtures are based on the 12 messages found in the user's
        # first live Gmail sync. None is proof of an application submitted
        # through JobPilot, so none may become a lifecycle event.
        samples = [
            (
                "₹1.44 lakh gratuity on a ₹50,000 basic, after year 5",
                "Naukri MINIs <info@minis.naukri.com>",
                "A gratuity explainer mentioning an employment offer letter.",
            ),
            (
                "Urgent Placement Drive - MOBIS India Ltd. | GET Role",
                "KLU Placements <placements4klu@gmail.com>",
                "Placement drive for ECE and EEE 2025 and 2026 batches. Register now.",
            ),
            (
                "Leaving our previous mails on read is costing you ₹25L",
                "LinkedIn x Unstop <noreply@unstop.news>",
                "Promotional message about previous emails and career opportunities.",
            ),
            (
                "Someone at Tata Consultancy Services you may know",
                "LinkedIn <messages-noreply@linkedin.com>",
                "You may know this person at Tata Consultancy Services.",
            ),
            (
                "Ready for your next big challenge? Trent Limited is hiring",
                "Sneha Kapoor <noreply@unstop.news>",
                "Trent Limited has a job opportunity. Apply now.",
            ),
            (
                "New Notice - !",
                "Superset <notifications@joinsuperset.com>",
                "Java developer who enjoys building real systems and solving real-world problems, this is your chance to put your skills to work and turn them into a career opportunity.",
            ),
            (
                "New Notice - !",
                "Superset <notifications@joinsuperset.com>",
                "Java developer who enjoys building real systems and solving real-world problems, this is your chance to put your skills to work and turn them into a career opportunity.",
            ),
            (
                "The AI that can't make things up.",
                "Why Join <whyjoin@substack.com>",
                "A newsletter about AI, hiring and assessment technology.",
            ),
            (
                "Important Opportunity: Microsoft and Meta Career & Placement Program",
                "Harshith G <harshith_g@shikshavertex.in>",
                "Career and placement program for college students. Register for the program.",
            ),
            (
                "Student Notice - Microsoft Training & Mentorship, AICTE & MSME Internship",
                "Harshith G <harshith_g@shikshavertex.in>",
                "Training and mentorship, internship with placement support. Register now.",
            ),
            (
                "upGrad Campus Hiring - Data Labeler - Remote",
                "KLU Placements <placements4klu@gmail.com>",
                "Campus hiring for 2025 and 2026 batches. Registration details inside.",
            ),
            (
                "$32 billion foreign capital inflow, L&T orders and more - Groww Digest",
                "Groww Digest <noreply@digest.groww.in>",
                "Your weekly financial newsletter and market digest.",
            ),
        ]
        for subject, sender, snippet in samples:
            with self.subTest(subject=subject):
                self.assertIsNone(
                    classify(subject=subject, sender=sender, snippet=snippet)
                )

    def test_saved_or_ready_application_cannot_be_matched(self) -> None:
        saved = self.client.post("/api/applications", json={"job_id": 2}).json()
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            match_id, confidence = self.email_module._application_match(
                connection,
                subject="Interview invitation for Backend Engineer at ExampleCo",
                sender="ExampleCo Recruiting <recruiting@exampleco.com>",
                snippet="We would like to invite you to interview for the Backend Engineer role.",
                body_text="We would like to invite you to interview for the Backend Engineer role at ExampleCo.",
            )
        finally:
            connection.close()
        self.assertIsNone(match_id)
        self.assertEqual(confidence, 0.0)
        self.assertEqual(saved["status"], "saved")

    def test_company_name_without_role_evidence_does_not_match(self) -> None:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            match_id, confidence = self.email_module._application_match(
                connection,
                subject="Interview invitation at ExampleCo",
                sender="ExampleCo Recruiting <recruiting@exampleco.com>",
                snippet="We would like to invite you to interview. Please choose a time.",
                body_text="We would like to invite you to interview. Please choose a time.",
            )
        finally:
            connection.close()
        self.assertIsNone(match_id)
        self.assertEqual(confidence, 0.0)

    def test_email_received_before_jobpilot_submission_cannot_match(self) -> None:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            match_id, confidence = self.email_module._application_match(
                connection,
                subject="Interview invitation for Software Engineer at ExampleCo",
                sender="ExampleCo Recruiting <recruiting@exampleco.com>",
                snippet="We would like to invite you to interview for the Software Engineer role.",
                body_text="We would like to invite you to interview for the Software Engineer role at ExampleCo.",
                received_at="2024-01-01T10:00:00+00:00",
            )
        finally:
            connection.close()
        self.assertIsNone(match_id)
        self.assertEqual(confidence, 0.0)

    def test_unmatched_lifecycle_email_is_not_added_to_pending_queue(self) -> None:
        message = _message(
            message_id="gmail-unmatched-role",
            subject="Interview invitation for Data Analyst at ExampleCo",
            body="We would like to invite you to interview for the Data Analyst role at ExampleCo.",
        )
        fake = _FakeGmailService(message)
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            sync = self.client.post("/api/email/sync", json={"max_messages": 10})
        self.assertEqual(sync.status_code, 200, sync.text)
        self.assertEqual(sync.json()["imported"], 0)
        self.assertEqual(sync.json()["unclassified"], 1)
        self.assertEqual(self.client.get("/api/email/events").json()["total"], 0)

    def test_review_cannot_apply_event_to_an_unsubmitted_application(self) -> None:
        saved = self.client.post("/api/applications", json={"job_id": 2}).json()
        fake = _FakeGmailService(_message(message_id="gmail-review-submitted-only"))
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"max_messages": 10})
        event = self.client.get("/api/email/events").json()["items"][0]
        response = self.client.post(
            f"/api/email/events/{event['id']}/review",
            json={"decision": "approve", "application_id": saved["id"]},
        )
        self.assertEqual(response.status_code, 409)

    def test_status_is_not_connected_without_token_and_oauth_config(self) -> None:
        response = self.client.get("/api/email/status")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["oauth_configured"])
        self.assertFalse(response.json()["connected"])
        self.assertEqual(response.json()["requested_scope"], "https://www.googleapis.com/auth/gmail.readonly")

    def test_oauth_start_reports_missing_google_client_file(self) -> None:
        response = self.client.get("/api/email/oauth/start")
        self.assertEqual(response.status_code, 503)
        self.assertIn("OAuth is not configured", response.json()["detail"])

    def test_sync_imports_pending_event_once_and_approval_updates_application(self) -> None:
        fake = _FakeGmailService(_message())
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            sync = self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 20})
            self.assertEqual(sync.status_code, 200, sync.text)
            self.assertEqual(sync.json()["imported"], 1)
            self.assertEqual(sync.json()["review_required"], 1)

            duplicate = self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 20})
            self.assertEqual(duplicate.status_code, 200, duplicate.text)
            self.assertEqual(duplicate.json()["imported"], 0)
            self.assertEqual(duplicate.json()["duplicates"], 1)

        events = self.client.get("/api/email/events").json()
        self.assertEqual(events["total"], 1)
        event = events["items"][0]
        self.assertEqual(event["event_type"], "interview_invitation")
        self.assertEqual(event["review_status"], "pending")
        self.assertEqual(event["matched_application_id"], self.application["id"])

        approved = self.client.post(
            f"/api/email/events/{event['id']}/review",
            json={"decision": "approve", "note": "Confirmed from the email."},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["before_status"], "applied")
        self.assertEqual(approved.json()["after_status"], "interview")
        self.assertTrue(approved.json()["application_status_changed"])

        tracked = self.client.get(f"/api/applications/{self.application['id']}")
        self.assertEqual(tracked.status_code, 200, tracked.text)
        self.assertEqual(tracked.json()["status"], "interview")

    def test_sync_persists_page_cursor_and_continues_on_next_manual_sync(self) -> None:
        first_message = _message(message_id="gmail-page-1")
        second_message = _message(message_id="gmail-page-2")
        pages = {
            None: {
                "messages": [{"id": "gmail-page-1", "threadId": "thread-1"}],
                "nextPageToken": "next-page-token",
            },
            "next-page-token": {
                "messages": [{"id": "gmail-page-2", "threadId": "thread-2"}],
            },
        }
        fake = _PagedFakeGmailService(
            {"gmail-page-1": first_message, "gmail-page-2": second_message},
            pages,
        )
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            first_sync = self.client.post(
                "/api/email/sync",
                json={"days_back": 90, "max_messages": 1},
            )
            self.assertEqual(first_sync.status_code, 200, first_sync.text)
            self.assertEqual(first_sync.json()["imported"], 1)
            self.assertTrue(first_sync.json()["more_pages_pending"])

            second_sync = self.client.post(
                "/api/email/sync",
                json={"days_back": 90, "max_messages": 1},
            )
            self.assertEqual(second_sync.status_code, 200, second_sync.text)
            self.assertEqual(second_sync.json()["imported"], 1)
            self.assertFalse(second_sync.json()["more_pages_pending"])

        self.assertNotIn("pageToken", fake._users.messages().list_calls[0])
        self.assertEqual(
            fake._users.messages().list_calls[1].get("pageToken"),
            "next-page-token",
        )
        events = self.client.get("/api/email/events?review_status=all").json()
        self.assertEqual(events["total"], 2)

    def test_ignoring_event_does_not_change_application(self) -> None:
        fake = _FakeGmailService(_message(message_id="gmail-message-ignore"))
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            sync = self.client.post("/api/email/sync", json={"max_messages": 10})
        self.assertEqual(sync.status_code, 200, sync.text)
        event = self.client.get("/api/email/events").json()["items"][0]
        ignored = self.client.post(
            f"/api/email/events/{event['id']}/review",
            json={"decision": "ignore", "note": "Not relevant to this application."},
        )
        self.assertEqual(ignored.status_code, 200, ignored.text)
        self.assertEqual(ignored.json()["review_status"], "ignored")
        tracked = self.client.get(f"/api/applications/{self.application['id']}").json()
        self.assertEqual(tracked["status"], "applied")

    def test_ambiguous_same_company_roles_are_not_guessed(self) -> None:
        second_application = self.client.post("/api/applications", json={"job_id": 2}).json()
        message = _message(
            message_id="gmail-message-ambiguous",
            subject="Interview invitation at ExampleCo",
            body="We would like to invite you to interview. Please choose a time.",
        )
        fake = _FakeGmailService(message)
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            sync = self.client.post("/api/email/sync", json={"max_messages": 10})
        self.assertEqual(sync.status_code, 200, sync.text)
        events = self.client.get("/api/email/events").json()["items"]
        # A lifecycle-like email without enough role evidence is not added to
        # the actionable queue at all.
        self.assertEqual(len(events), 0)
        self.assertNotEqual(self.application["id"], second_application["id"])

    def test_event_must_be_reviewed_before_status_changes_and_cannot_be_approved_twice(self) -> None:
        fake = _FakeGmailService(_message())
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"max_messages": 10})
        event = self.client.get("/api/email/events").json()["items"][0]
        self.assertEqual(self.client.get(f"/api/applications/{self.application['id']}").json()["status"], "applied")
        payload = {"decision": "approve"}
        first = self.client.post(f"/api/email/events/{event['id']}/review", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(f"/api/email/events/{event['id']}/review", json=payload)
        self.assertEqual(second.status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)
