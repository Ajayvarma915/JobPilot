from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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


def _message(*, message_id: str = "gmail-message-1", subject: str | None = None, body: str | None = None, sender: str | None = None) -> dict:
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
                {"name": "From", "value": sender or "ExampleCo Recruiting <recruiting@exampleco.com>"},
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
        from app.email.untracked import router as untracked_router

        cls.app.include_router(untracked_router)
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
        # These tests exercise the manual approval path; the automatic path has its own tests below.
        self.client.put("/api/email/settings", json={"auto_update": False})
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

    def test_confirmation_for_an_untracked_job_becomes_a_suggestion_you_approve(self) -> None:
        """A referral application the user never saved (for example a Qualcomm one) is suggested, never added silently."""
        message = _message(
            message_id="gmail-qualcomm-confirmation",
            subject="Successfully submitted application for Ajay Varma Kammampati",
            sender="qualcomm@myworkday.com",
            body="Thank you for choosing Qualcomm. We have received your application for the position Associate Engineer - 3098178 . "
                 "Our team is currently reviewing your profile.",
        )
        fake = _FakeGmailService(message)
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"max_messages": 10})
        before = self.client.get("/api/applications").json()["total"]
        self.assertEqual(self.client.get("/api/email/events").json()["total"], 0, "it is not a tracker event")
        pending = self.client.get("/api/email/suggestions").json()["items"]
        self.assertEqual([(s["company_guess"], s["title_guess"]) for s in pending], [("Qualcomm", "Associate Engineer")])
        self.assertEqual(self.client.get("/api/applications").json()["total"], before, "nothing is tracked until the user adds it")

        added = self.client.post(f"/api/email/suggestions/{pending[0]['id']}/add", json={"company": "Qualcomm", "title": "Associate Engineer"})
        self.assertEqual(added.status_code, 201, added.text)
        application = self.client.get(f"/api/applications/{added.json()['application_id']}").json()
        self.assertEqual((application["status"], application["job"]["company"], application["job"]["title"]),
                         ("applied", "Qualcomm", "Associate Engineer"))
        self.assertEqual(self.client.post(f"/api/email/suggestions/{pending[0]['id']}/add", json={"company": "Qualcomm", "title": "x"}).status_code, 409)
        self.assertEqual(self.client.get("/api/email/suggestions").json()["items"], [], "an added suggestion leaves the pending list")

    def test_only_confirmations_are_suggested_and_dismiss_works(self) -> None:
        rejection = _message(message_id="gmail-untracked-rejection", subject="Update on your application",
                             body="We regret to inform you that your application for the Data Analyst role was not successful.")
        confirmation = _message(message_id="gmail-untracked-confirmation", sender="Initech Careers <careers@initech.com>",
                                subject="Thank you for applying", body="Thank you for applying to the Platform Engineer role at Initech.")
        fake = _PagedFakeGmailService(
            {"gmail-untracked-rejection": rejection, "gmail-untracked-confirmation": confirmation},
            {None: {"messages": [{"id": "gmail-untracked-rejection", "threadId": "a"}, {"id": "gmail-untracked-confirmation", "threadId": "b"}]}},
        )
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"max_messages": 10})
        items = self.client.get("/api/email/suggestions").json()["items"]
        self.assertEqual([s["company_guess"] for s in items if s["gmail_message_id"] == "gmail-untracked-confirmation"], ["Initech"])
        self.assertFalse([s for s in items if s["gmail_message_id"] == "gmail-untracked-rejection"], "other mail kinds are not suggested")
        target = next(s for s in items if s["gmail_message_id"] == "gmail-untracked-confirmation")
        self.assertEqual(self.client.post(f"/api/email/suggestions/{target['id']}/dismiss").status_code, 200)
        self.assertFalse([s for s in self.client.get("/api/email/suggestions").json()["items"] if s["id"] == target["id"]])

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

    def _match(self, **overrides):
        arguments = dict(
            subject="Interview invitation for Software Engineer at ExampleCo",
            sender="ExampleCo Recruiting <recruiting@exampleco.com>",
            snippet="We would like to invite you to interview for the Software Engineer role.",
            body_text="We would like to invite you to interview for the Software Engineer role at ExampleCo.",
            received_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        arguments.update(overrides)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            return self.email_module._application_match(connection, **arguments)
        finally:
            connection.close()

    def test_reply_still_matches_after_the_posting_is_taken_down(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("UPDATE jobs SET is_active = 0 WHERE id = 1")
            connection.commit()
        finally:
            connection.close()
        try:
            match_id, confidence = self._match()
        finally:
            connection = sqlite3.connect(self.database_path)
            connection.execute("UPDATE jobs SET is_active = 1 WHERE id = 1")
            connection.commit()
            connection.close()
        self.assertEqual(match_id, self.application["id"], "interviews and rejections arrive after postings close")
        self.assertGreaterEqual(confidence, 0.78)

    def test_message_without_a_usable_date_never_matches(self) -> None:
        for received_at in (None, "", "not a date"):
            with self.subTest(received_at=received_at):
                self.assertEqual(self._match(received_at=received_at), (None, 0.0))
        self.assertIsNotNone(self._match()[0], "the same message with a valid date does match")

    def test_rfc2822_date_header_is_understood(self) -> None:
        received = self.email_module._received_at({}, {"date": "Mon, 16 Nov 2026 10:00:00 +0530"})
        self.assertEqual(received, "2026-11-16T04:30:00+00:00")
        self.assertIsNone(self.email_module._received_at({}, {"date": "garbage"}))
        self.assertEqual(
            self.email_module._received_at({"internalDate": "1700000000000"}, {"date": "garbage"}),
            "2023-11-14T22:13:20+00:00",
        )

    def test_approval_suggests_a_follow_up_without_overwriting_the_users_own(self) -> None:
        fake = _FakeGmailService(_message())
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 20})
        event = self.client.get("/api/email/events").json()["items"][0]
        before = self.client.get(f"/api/applications/{self.application['id']}").json()
        self.assertFalse(before["next_action"] or before["follow_up_date"], "nothing is scheduled before approval")
        self.client.post(f"/api/email/events/{event['id']}/review", json={"decision": "approve"})
        after = self.client.get(f"/api/applications/{self.application['id']}").json()
        self.assertEqual(after["status"], "interview")
        self.assertEqual(after["next_action"], "Prepare for and attend the interview")
        self.assertEqual(after["follow_up_date"], (datetime.now().date() + timedelta(days=5)).isoformat())

        # A next action the user already wrote is kept.
        self.client.patch(f"/api/applications/{self.application['id']}", json={"status": "applied"})
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("UPDATE applications SET status='applied', next_action='My own plan', follow_up_date='2030-01-01' WHERE id=?", (self.application["id"],))
            connection.execute("UPDATE application_email_events SET review_status='pending', reviewed_at=NULL WHERE id=?", (event["id"],))
            connection.commit()
        finally:
            connection.close()
        self.client.post(f"/api/email/events/{event['id']}/review", json={"decision": "approve"})
        kept = self.client.get(f"/api/applications/{self.application['id']}").json()
        self.assertEqual((kept["next_action"], kept["follow_up_date"]), ("My own plan", "2030-01-01"))

    def test_stored_event_keeps_only_minimal_text(self) -> None:
        long_body = "We would like to invite you to interview for the Software Engineer role at ExampleCo. " + ("Private detail. " * 400)
        fake = _FakeGmailService(_message(body=long_body))
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 20})
        connection = sqlite3.connect(self.database_path)
        try:
            rows = connection.execute("SELECT subject, sender, snippet FROM application_email_events").fetchall()
            columns = [r[1] for r in connection.execute("PRAGMA table_info(application_email_events)")]
        finally:
            connection.close()
        self.assertEqual(len(rows), 1)
        self.assertLessEqual(len(rows[0][2]), 1200, "only a short snippet is stored")
        self.assertNotIn("Private detail. " * 20, " ".join(rows[0]), "the body is not stored")
        self.assertFalse({"body", "body_text", "raw", "html"} & set(columns), f"no body column exists: {columns}")

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

        # Each sync now starts from the newest page (so new mail is never skipped) and then continues
        # through the older backlog from the stored position.
        calls = fake._users.messages().list_calls
        self.assertNotIn("pageToken", calls[0])
        self.assertNotIn("pageToken", calls[1], "the second sync looks at the newest page first")
        self.assertEqual(calls[2].get("pageToken"), "next-page-token", "then it continues the older backlog")
        events = self.client.get("/api/email/events?review_status=all").json()
        self.assertEqual(events["total"], 2)

    def test_mail_that_arrives_after_a_stored_cursor_is_still_scanned(self) -> None:
        """Regression: once a sync stored its older-messages position, later syncs only walked
        further back and never looked at mail that arrived since (a real referral and application
        confirmation were missed)."""
        messages = {"gmail-old-1": _message(message_id="gmail-old-1"), "gmail-old-2": _message(message_id="gmail-old-2")}
        pages = {
            None: {"messages": [{"id": "gmail-old-1", "threadId": "t1"}], "nextPageToken": "older"},
            "older": {"messages": [{"id": "gmail-old-2", "threadId": "t2"}]},
        }
        fake = _PagedFakeGmailService(messages, pages)
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 1})  # stores the cursor
            messages["gmail-new"] = _message(message_id="gmail-new")
            pages[None] = {"messages": [{"id": "gmail-new", "threadId": "t3"}, {"id": "gmail-old-1", "threadId": "t1"}],
                           "nextPageToken": "older"}
            result = self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 5}).json()
        self.assertEqual(result["imported"], 2, "the new message and the remaining older one are both imported")
        ids = {row["gmail_message_id"] for row in self.client.get("/api/email/events?review_status=all").json()["items"]}
        self.assertIn("gmail-new", ids)
        self.assertFalse(result["more_pages_pending"])

    # ---- automatic updates -------------------------------------------------------------------------------
    def _sync_one(self, message: dict) -> dict:
        fake = _FakeGmailService(message)
        with patch.object(self.email_module, "_gmail_service", return_value=fake):
            response = self.client.post("/api/email/sync", json={"days_back": 90, "max_messages": 10})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _track(self, job_id: int, status: str = "saved") -> dict:
        existing = self.client.get(f"/api/applications/by-job/{job_id}")
        if existing.status_code == 200:
            self.client.delete(f"/api/applications/{existing.json()['id']}")
        return self.client.post("/api/applications", json={"job_id": job_id, "status": status}).json()

    def test_shortlisting_and_scheduling_phrases_are_recognised(self) -> None:
        classify = self.email_module.classify_email
        shortlisted = classify(subject="Update", body_text="Good news: you have been shortlisted for the Software Engineer role at ExampleCo.")
        self.assertEqual((shortlisted["event_type"], shortlisted["proposed_status"]), ("assessment_invitation", "assessment"))
        scheduled = classify(subject="Next step", body_text="Your interview has been scheduled for Tuesday 11 am for the Software Engineer role.")
        self.assertEqual(scheduled["event_type"], "interview_invitation")
        # ordinary newsletters and job ads still do not count
        self.assertIsNone(classify(subject="Top jobs for you", body_text="Shortlisted companies hiring this week: apply now to 20 openings."))
        self.assertIsNone(classify(subject="HackerRank digest", body_text="Practice coding challenge of the week and improve your rank."))

    def test_settings_default_on_and_can_be_turned_off(self) -> None:
        self.client.put("/api/email/settings", json={"auto_update": True})
        self.assertTrue(self.client.get("/api/email/settings").json()["auto_update"])
        self.assertFalse(self.client.put("/api/email/settings", json={"auto_update": False}).json()["auto_update"])
        self.assertFalse(self.client.get("/api/email/settings").json()["auto_update"])

    def test_confirmation_email_marks_a_tracked_job_as_applied_automatically(self) -> None:
        """The whole point: track a job, apply on the company site, and the confirmation email marks it Applied."""
        self.client.put("/api/email/settings", json={"auto_update": True})
        saved = self._track(2, "saved")
        self.assertEqual(saved["status"], "saved")
        result = self._sync_one(_message(
            message_id="gmail-auto-confirm", subject="We received your application",
            body="Thank you. We have received your application for the Backend Engineer role at ExampleCo."))
        self.assertEqual((result["imported"], result["auto_applied"], result["review_required"]), (1, 1, 0), result)
        application = self.client.get(f"/api/applications/{saved['id']}").json()
        self.assertEqual(application["status"], "applied")
        self.assertTrue(application["applied_at"], "the application time is recorded")
        approved = self.client.get("/api/email/events", params={"review_status": "approved"}).json()["items"]
        self.assertEqual(len(approved), 1)
        self.assertEqual((approved[0]["before_status"], approved[0]["after_status"]), ("saved", "applied"))
        self.assertIn("automatically", approved[0]["review_note"])

    def test_with_automatic_updates_off_the_same_email_waits_for_approval(self) -> None:
        self.client.put("/api/email/settings", json={"auto_update": False})
        saved = self._track(2, "ready_to_apply")
        result = self._sync_one(_message(
            message_id="gmail-manual-confirm", subject="We received your application",
            body="Thank you. We have received your application for the Backend Engineer role at ExampleCo."))
        self.assertEqual((result["imported"], result["auto_applied"], result["review_required"]), (1, 0, 1), result)
        self.assertEqual(self.client.get(f"/api/applications/{saved['id']}").json()["status"], "ready_to_apply")
        event = self.client.get("/api/email/events").json()["items"][0]
        self.assertEqual(event["matched_job"]["application_id"], saved["id"])
        approve = self.client.post(f"/api/email/events/{event['id']}/review", json={"decision": "approve"})
        self.assertEqual(approve.status_code, 200, approve.text)
        self.assertEqual(self.client.get(f"/api/applications/{saved['id']}").json()["status"], "applied")

    def test_only_a_confirmation_can_move_a_not_yet_applied_job(self) -> None:
        self.client.put("/api/email/settings", json={"auto_update": True})
        self._track(2, "saved")
        result = self._sync_one(_message(
            message_id="gmail-interview-for-unapplied", subject="Interview invitation for Backend Engineer",
            body="We would like to invite you to interview for the Backend Engineer role at ExampleCo."))
        self.assertEqual((result["imported"], result["auto_applied"]), (0, 0), "an interview email cannot prove you applied")
        self.assertEqual(self.client.get("/api/applications/by-job/2").json()["status"], "saved")

    def test_interview_email_moves_an_applied_job_forward_automatically(self) -> None:
        self.client.put("/api/email/settings", json={"auto_update": True})
        result = self._sync_one(_message(message_id="gmail-auto-interview"))  # default text: interview for Software Engineer at ExampleCo
        self.assertEqual((result["imported"], result["auto_applied"], result["review_required"]), (1, 1, 0), result)
        application = self.client.get(f"/api/applications/{self.application['id']}").json()
        self.assertEqual(application["status"], "interview")
        self.assertEqual(application["next_action"], "Prepare for and attend the interview")

    def test_a_weak_match_is_never_applied_automatically(self) -> None:
        self.client.put("/api/email/settings", json={"auto_update": True})
        result = self._sync_one(_message(
            message_id="gmail-weak", subject="Interview invitation", body="We would like to invite you to interview for a role at ExampleCo."))
        self.assertEqual(result["auto_applied"], 0, result)
        self.assertEqual(self.client.get(f"/api/applications/{self.application['id']}").json()["status"], "applied")

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
