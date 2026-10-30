from __future__ import annotations

import base64
import html
import json
import logging
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path as ApiPath, Query, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.applications.tracker import get_application_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/email", tags=["email"])

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SCOPES = [GMAIL_READONLY_SCOPE]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OAUTH_STATE_TTL_MINUTES = 10
MAX_EMAIL_BODY_CHARS = 40_000
MAX_STORED_SNIPPET_CHARS = 1_200

EmailEventType = Literal[
    "application_confirmation",
    "assessment_invitation",
    "interview_invitation",
    "offer",
    "rejection",
]
ReviewDecision = Literal["approve", "ignore"]

APPLICATION_STATUS_ORDER = {
    "saved": 0,
    "preparing": 1,
    "ready_to_apply": 2,
    "applied": 3,
    "assessment": 4,
    "interview": 5,
    "offer": 6,
    "rejected": 6,
    "withdrawn": 6,
}
TERMINAL_APPLICATION_STATUSES = {"offer", "rejected", "withdrawn"}
PROPOSED_STATUS_BY_EVENT = {
    "application_confirmation": "applied",
    "assessment_invitation": "assessment",
    "interview_invitation": "interview",
    "offer": "offer",
    "rejection": "rejected",
}


class GmailSyncRequest(BaseModel):
    days_back: int = Field(default=180, ge=1, le=365)
    max_messages: int = Field(default=100, ge=1, le=500)


class EmailEventReviewRequest(BaseModel):
    decision: ReviewDecision
    application_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=1_000)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() in {"script", "style", "head", "title"}:
            self._skip_depth += 1
        elif tag.lower() in {"br", "p", "div", "li", "tr"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head", "title"} and self._skip_depth:
            self._skip_depth -= 1
        elif tag.lower() in {"p", "div", "li", "tr"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def _database_path() -> Path:
    configured = os.getenv("JOBPILOT_DATABASE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "jobpilot.db"


def _client_secrets_path() -> Path:
    configured = os.getenv("JOBPILOT_GOOGLE_CLIENT_SECRETS")
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "credentials" / "gmail_oauth_client.json"


def _token_path() -> Path:
    configured = os.getenv("JOBPILOT_GMAIL_TOKEN_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / "tokens" / "gmail_token.json"


def _oauth_redirect_uri() -> str:
    configured = os.getenv("JOBPILOT_GMAIL_REDIRECT_URI")
    if configured:
        return configured.strip()
    return "http://127.0.0.1:8000/api/email/oauth/callback"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_email_schema(connection: sqlite3.Connection) -> None:
    """Create only email-integration tables; never alter job/application rows."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS email_oauth_states (
            state TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS email_sync_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            email_address TEXT,
            connected_at TEXT,
            last_sync_at TEXT,
            last_sync_imported INTEGER NOT NULL DEFAULT 0,
            last_sync_scanned INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_page_token TEXT,
            sync_query_days_back INTEGER
        );

        CREATE TABLE IF NOT EXISTS email_scanned_messages (
            gmail_message_id TEXT PRIMARY KEY,
            gmail_thread_id TEXT,
            processed_at TEXT NOT NULL,
            disposition TEXT NOT NULL CHECK (disposition IN ('event', 'unclassified'))
        );

        CREATE TABLE IF NOT EXISTS application_email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT NOT NULL UNIQUE,
            gmail_thread_id TEXT,
            received_at TEXT,
            sender TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            snippet TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL CHECK (event_type IN (
                'application_confirmation',
                'assessment_invitation',
                'interview_invitation',
                'offer',
                'rejection'
            )),
            classification_confidence REAL NOT NULL,
            matched_application_id INTEGER,
            match_confidence REAL NOT NULL DEFAULT 0,
            proposed_status TEXT NOT NULL CHECK (proposed_status IN (
                'applied', 'assessment', 'interview', 'offer', 'rejected'
            )),
            review_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (review_status IN ('pending', 'approved', 'ignored')),
            review_note TEXT,
            before_status TEXT,
            after_status TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (matched_application_id)
                REFERENCES applications(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS ix_email_events_review_status
            ON application_email_events(review_status, received_at);
        CREATE INDEX IF NOT EXISTS ix_email_events_application
            ON application_email_events(matched_application_id, received_at);
        """
    )

    # Additive migration for databases created by earlier iterations of the
    # Gmail integration. CREATE TABLE IF NOT EXISTS does not add new columns.
    sync_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(email_sync_state)").fetchall()
    }
    if "next_page_token" not in sync_columns:
        connection.execute("ALTER TABLE email_sync_state ADD COLUMN next_page_token TEXT")
    if "sync_query_days_back" not in sync_columns:
        connection.execute("ALTER TABLE email_sync_state ADD COLUMN sync_query_days_back INTEGER")

    # Preserve idempotency for events imported before the scanned-message index existed.
    connection.execute(
        """
        INSERT OR IGNORE INTO email_scanned_messages (
            gmail_message_id, gmail_thread_id, processed_at, disposition
        )
        SELECT gmail_message_id, gmail_thread_id, created_at, 'event'
        FROM application_email_events
        """
    )
    connection.commit()


def _credentials_file_configured() -> bool:
    return _client_secrets_path().is_file()


def _google_flow(state: str | None = None) -> Any:
    secrets_path = _client_secrets_path()
    if not secrets_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail OAuth is not configured. Add your Google OAuth web-client "
                "JSON at credentials/gmail_oauth_client.json or set "
                "JOBPILOT_GOOGLE_CLIENT_SECRETS."
            ),
        )
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail dependencies are not installed. Run the documented pip "
                "install command for google-api-python-client, "
                "google-auth-httplib2, and google-auth-oauthlib."
            ),
        ) from exc

    try:
        flow = Flow.from_client_secrets_file(
            str(secrets_path),
            scopes=GMAIL_SCOPES,
            state=state,
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The Google OAuth client JSON could not be read. Verify that "
                "it is a valid Web application OAuth client file."
            ),
        ) from exc
    flow.redirect_uri = _oauth_redirect_uri()
    return flow


def _save_token(credentials: Any) -> None:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(credentials.to_json(), encoding="utf-8")
    try:
        os.chmod(temporary_path, 0o600)
    except OSError:
        # Windows ACLs govern access there; chmod is best-effort cross-platform.
        pass
    temporary_path.replace(path)


def _load_credentials() -> Any:
    path = _token_path()
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Gmail is not connected. Open /api/email/oauth/start first.",
        )

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail dependencies are not installed. Install the Google API "
                "client packages listed in requirements.txt."
            ),
        ) from exc

    try:
        credentials = Credentials.from_authorized_user_file(
            str(path),
            GMAIL_SCOPES,
        )
        if not credentials.has_scopes(GMAIL_SCOPES):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    "The saved Google authorization lacks Gmail read-only access. "
                    "Disconnect Gmail and authorize again."
                ),
            )
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
                _save_token(credentials)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=(
                        "The saved Gmail authorization is no longer valid. "
                        "Disconnect Gmail and reconnect it."
                    ),
                )
        return credentials
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Could not load Gmail credentials: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Gmail authorization could not be refreshed. Disconnect Gmail "
                "and reconnect it."
            ),
        ) from exc


def _gmail_service() -> Any:
    credentials = _load_credentials()
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gmail API dependencies are missing. Install the Google API "
                "client packages listed in requirements.txt."
            ),
        ) from exc

    try:
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        logger.warning("Could not initialize Gmail API client: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Gmail API client could not be initialized.",
        ) from exc


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def classify_email(
    *,
    subject: str = "",
    sender: str = "",
    snippet: str = "",
    body_text: str = "",
) -> dict[str, Any] | None:
    """Classify a small set of recruiting events without sending email data to an LLM."""
    text = _normalise_text(" ".join((subject, sender, snippet, body_text)))
    if not text:
        return None

    rules: tuple[tuple[str, tuple[str, ...], float], ...] = (
        (
            "offer",
            (
                "pleased to offer you",
                "offer of employment",
                "employment offer",
                "offer letter",
                "formal offer",
                "congratulations on your offer",
                "we would like to offer",
            ),
            0.96,
        ),
        (
            "rejection",
            (
                "not moving forward",
                "decided to move forward with other candidates",
                "moving forward with other candidates",
                "unable to move forward",
                "not selected for",
                "will not be moving forward",
                "will not be proceeding",
                "application was unsuccessful",
                "regret to inform you",
                "we have decided not to proceed",
                "your application has been declined",
            ),
            0.94,
        ),
        (
            "assessment_invitation",
            (
                "online assessment",
                "coding assessment",
                "technical assessment",
                "assessment invitation",
                "complete the assessment",
                "complete your assessment",
                "coding challenge",
                "take home assignment",
                "take home assessment",
                "hackerrank",
                "codility",
                "online test",
                "assessment link",
            ),
            0.91,
        ),
        (
            "interview_invitation",
            (
                "interview invitation",
                "invite you to interview",
                "invited to interview",
                "schedule an interview",
                "schedule your interview",
                "interview availability",
                "technical interview",
                "phone screen",
                "recruiter screen",
                "interview for the",
                "interview for your",
                "would like to interview",
                "first round interview",
                "next round interview",
            ),
            0.91,
        ),
        (
            "application_confirmation",
            (
                "thank you for applying",
                "thank you for your application",
                "application received",
                "received your application",
                "application confirmation",
                "successfully submitted your application",
                "we have your application",
            ),
            0.90,
        ),
    )

    for event_type, phrases, confidence in rules:
        if any(phrase in text for phrase in phrases):
            return {
                "event_type": event_type,
                "confidence": confidence,
                "proposed_status": PROPOSED_STATUS_BY_EVENT[event_type],
            }

    # Lower-confidence patterns catch common variations without treating every
    # email that merely mentions a job as an event.
    if "interview" in text and any(word in text for word in ("invite", "invitation", "schedule", "availability")):
        event_type = "interview_invitation"
        return {
            "event_type": event_type,
            "confidence": 0.76,
            "proposed_status": PROPOSED_STATUS_BY_EVENT[event_type],
        }
    if "assessment" in text and any(word in text for word in ("complete", "deadline", "invitation", "link", "due")):
        event_type = "assessment_invitation"
        return {
            "event_type": event_type,
            "confidence": 0.75,
            "proposed_status": PROPOSED_STATUS_BY_EVENT[event_type],
        }
    return None


def _extract_body_text(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def visit(part: dict[str, Any]) -> None:
        # Never download attachments. Recruiting event detection only needs text.
        if part.get("filename"):
            return
        mime_type = str(part.get("mimeType", "")).lower()
        body = part.get("body") or {}
        data = body.get("data")
        if data and mime_type in {"text/plain", "text/html"}:
            try:
                decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                text_value = decoded.decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                text_value = ""
            if mime_type == "text/plain":
                plain_parts.append(text_value)
            else:
                html_parts.append(text_value)
        for child in part.get("parts", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(payload)
    if plain_parts:
        raw_text = "\n".join(plain_parts)
    elif html_parts:
        parser = _HTMLTextExtractor()
        parser.feed("\n".join(html_parts))
        raw_text = " ".join(parser.parts)
    else:
        raw_text = ""
    return re.sub(r"\s+", " ", html.unescape(raw_text)).strip()[:MAX_EMAIL_BODY_CHARS]


def _message_headers(payload: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in (payload or {}).get("headers", []) or []:
        name = str(item.get("name", "")).strip().lower()
        if name and name not in result:
            result[name] = str(item.get("value", "")).strip()
    return result


def _received_at(message: dict[str, Any], headers: dict[str, str]) -> str | None:
    internal_date = message.get("internalDate")
    if internal_date is not None:
        try:
            return datetime.fromtimestamp(
                int(internal_date) / 1000,
                tz=timezone.utc,
            ).isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError, OverflowError):
            pass
    date_header = headers.get("date")
    if date_header:
        try:
            parsed = datetime.fromisoformat(date_header.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            return None
    return None


def _title_overlap(title: str, corpus: str) -> float:
    stop_words = {
        "the", "and", "for", "with", "from", "your", "you", "our", "this",
        "that", "job", "role", "position", "opening", "career", "careers",
        "engineer", "engineering", "developer", "development", "intern", "internship",
        "senior", "junior", "associate", "lead", "staff", "principal", "level",
        "apply", "application", "team", "remote", "hybrid", "onsite", "india",
    }
    tokens = {
        token
        for token in _normalise_text(title).split()
        if len(token) > 2 and token not in stop_words
    }
    if not tokens:
        return 0.0
    corpus_tokens = set(_normalise_text(corpus).split())
    return len(tokens & corpus_tokens) / len(tokens)


def _application_match(
    connection: sqlite3.Connection,
    *,
    subject: str,
    sender: str,
    snippet: str,
    body_text: str,
) -> tuple[int | None, float]:
    corpus = _normalise_text(" ".join((subject, sender, snippet, body_text)))
    if not corpus:
        return None, 0.0

    rows = connection.execute(
        """
        SELECT a.id AS application_id, a.status, j.title AS job_title,
               c.name AS company_name
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN companies c ON c.id = j.company_id
        WHERE a.status NOT IN ('withdrawn') AND j.is_active = 1
        ORDER BY a.updated_at DESC, a.id DESC
        """
    ).fetchall()

    candidates: list[tuple[int, float, float, str]] = []
    corpus_words = set(corpus.split())
    for row in rows:
        company = _normalise_text(row["company_name"] or "")
        if not company:
            continue
        company_tokens = [token for token in company.split() if len(token) > 2]
        exact_company = f" {company} " in f" {corpus} "
        if exact_company:
            company_score = 0.70
        elif company_tokens and len(company_tokens) > 1:
            covered = sum(token in corpus_words for token in company_tokens) / len(company_tokens)
            if covered < 0.75:
                continue
            company_score = 0.52 * covered
        elif len(company) >= 4 and company in corpus_words:
            company_score = 0.54
        else:
            continue

        overlap = _title_overlap(row["job_title"] or "", corpus)
        score = min(0.98, company_score + (0.26 * overlap))
        candidates.append((int(row["application_id"]), score, overlap, company))

    if not candidates:
        return None, 0.0

    # If multiple saved roles belong to the same company, require job-title
    # evidence before proposing a specific application.
    candidates.sort(key=lambda item: (item[1], item[2]), reverse=True)
    best = candidates[0]
    same_company_candidates = [item for item in candidates if item[3] == best[3]]
    if len(same_company_candidates) > 1:
        if best[2] < 0.5:
            return None, 0.0
        if len(same_company_candidates) > 1 and abs(best[1] - same_company_candidates[1][1]) < 0.08:
            return None, 0.0

    if best[1] < 0.60:
        return None, best[1]
    return best[0], best[1]


def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "gmail_message_id": row["gmail_message_id"],
        "gmail_thread_id": row["gmail_thread_id"],
        "received_at": row["received_at"],
        "sender": row["sender"],
        "subject": row["subject"],
        "snippet": row["snippet"],
        "event_type": row["event_type"],
        "classification_confidence": row["classification_confidence"],
        "matched_application_id": row["matched_application_id"],
        "match_confidence": row["match_confidence"],
        "proposed_status": row["proposed_status"],
        "review_status": row["review_status"],
        "review_note": row["review_note"],
        "before_status": row["before_status"],
        "after_status": row["after_status"],
        "reviewed_at": row["reviewed_at"],
        "created_at": row["created_at"],
        "matched_job": (
            {
                "application_id": row["matched_application_id"],
                "company": row["company_name"],
                "title": row["job_title"],
                "current_status": row["current_application_status"],
            }
            if row["matched_application_id"] is not None
            else None
        ),
    }


def _email_event_query(where_clause: str = "") -> str:
    return f"""
        SELECT e.*, c.name AS company_name, j.title AS job_title,
               a.status AS current_application_status
        FROM application_email_events e
        LEFT JOIN applications a ON a.id = e.matched_application_id
        LEFT JOIN jobs j ON j.id = a.job_id
        LEFT JOIN companies c ON c.id = j.company_id
        {where_clause}
    """


def _record_message(
    connection: sqlite3.Connection,
    message: dict[str, Any],
) -> str:
    message_id = str(message.get("id", "")).strip()
    if not message_id:
        return "invalid"
    exists = connection.execute(
        "SELECT 1 FROM email_scanned_messages WHERE gmail_message_id = ?",
        (message_id,),
    ).fetchone()
    if exists:
        return "duplicate"

    payload = message.get("payload") or {}
    headers = _message_headers(payload)
    subject = headers.get("subject", "")[:500]
    sender = headers.get("from", "")[:500]
    snippet = str(message.get("snippet", ""))[:MAX_STORED_SNIPPET_CHARS]
    body_text = _extract_body_text(payload)
    classification = classify_email(
        subject=subject,
        sender=sender,
        snippet=snippet,
        body_text=body_text,
    )
    if classification is None:
        connection.execute(
            """
            INSERT OR IGNORE INTO email_scanned_messages (
                gmail_message_id, gmail_thread_id, processed_at, disposition
            ) VALUES (?, ?, ?, 'unclassified')
            """,
            (message_id, str(message.get("threadId", ""))[:255] or None, _utc_now()),
        )
        return "unclassified"

    matched_application_id, match_confidence = _application_match(
        connection,
        subject=subject,
        sender=sender,
        snippet=snippet,
        body_text=body_text,
    )
    received_at = _received_at(message, headers)
    connection.execute(
        """
        INSERT INTO application_email_events (
            gmail_message_id, gmail_thread_id, received_at, sender, subject,
            snippet, event_type, classification_confidence,
            matched_application_id, match_confidence, proposed_status,
            review_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            message_id,
            str(message.get("threadId", ""))[:255] or None,
            received_at,
            sender,
            subject,
            snippet,
            classification["event_type"],
            classification["confidence"],
            matched_application_id,
            match_confidence,
            classification["proposed_status"],
            _utc_now(),
        ),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO email_scanned_messages (
            gmail_message_id, gmail_thread_id, processed_at, disposition
        ) VALUES (?, ?, ?, 'event')
        """,
        (message_id, str(message.get("threadId", ""))[:255] or None, _utc_now()),
    )
    return "imported"


def _gmail_query(days_back: int) -> str:
    # Gmail search syntax is deliberately kept narrow to avoid importing the
    # entire inbox. Search is read-only and never fetches attachments.
    return (
        f"newer_than:{days_back}d "
        "{application interview assessment offer rejection recruiter hiring}"
    )


@router.get("/status")
def get_email_status(
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _ensure_email_schema(connection)
    row = connection.execute(
        "SELECT * FROM email_sync_state WHERE id = 1"
    ).fetchone()
    return {
        "provider": "gmail",
        "oauth_configured": _credentials_file_configured(),
        "connected": bool(_token_path().is_file() and row and row["email_address"]),
        "email_address": row["email_address"] if row else None,
        "connected_at": row["connected_at"] if row else None,
        "last_sync_at": row["last_sync_at"] if row else None,
        "last_sync_imported": row["last_sync_imported"] if row else 0,
        "last_sync_scanned": row["last_sync_scanned"] if row else 0,
        "last_error": row["last_error"] if row else None,
        "requested_scope": GMAIL_READONLY_SCOPE,
        "stores_full_email_body": False,
    }


@router.get("/oauth/start")
def start_gmail_oauth(
    connection: sqlite3.Connection = Depends(get_application_db),
) -> RedirectResponse:
    _ensure_email_schema(connection)
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    created_at = now.isoformat(timespec="seconds")
    expires_at = (now + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)).isoformat(timespec="seconds")
    connection.execute(
        "DELETE FROM email_oauth_states WHERE expires_at < ?",
        (created_at,),
    )
    connection.execute(
        "INSERT INTO email_oauth_states(state, created_at, expires_at) VALUES (?, ?, ?)",
        (state, created_at, expires_at),
    )
    connection.commit()

    flow = _google_flow(state)
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    response = RedirectResponse(authorization_url, status_code=302)
    response.set_cookie(
        key="jobpilot_gmail_oauth_state",
        value=state,
        httponly=True,
        secure=_oauth_redirect_uri().startswith("https://"),
        samesite="lax",
        max_age=OAUTH_STATE_TTL_MINUTES * 60,
        path="/api/email/oauth",
    )
    return response


@router.get("/oauth/callback", response_class=HTMLResponse)
def complete_gmail_oauth(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    jobpilot_gmail_oauth_state: str | None = Cookie(default=None),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> HTMLResponse:
    _ensure_email_schema(connection)
    if error:
        response = HTMLResponse(
            "<h2>JobPilot Gmail connection was not completed</h2>"
            "<p>Authorization was cancelled or denied. You can close this tab.</p>",
            status_code=400,
        )
        response.delete_cookie("jobpilot_gmail_oauth_state", path="/api/email/oauth")
        return response

    if not state or not jobpilot_gmail_oauth_state or not secrets.compare_digest(
        state,
        jobpilot_gmail_oauth_state,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Gmail OAuth state could not be verified. Start the connection again.",
        )

    state_row = connection.execute(
        "SELECT expires_at FROM email_oauth_states WHERE state = ?",
        (state,),
    ).fetchone()
    connection.execute("DELETE FROM email_oauth_states WHERE state = ?", (state,))
    connection.commit()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not state_row or state_row["expires_at"] < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The Gmail OAuth request expired. Start the connection again.",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google did not return an authorization code.",
        )

    flow = _google_flow(state)
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        service = _service_for_credentials(credentials)
        profile = service.users().getProfile(userId="me").execute()
        email_address = str(profile.get("emailAddress", "")).strip()
        if not email_address:
            raise ValueError("Google returned no Gmail address")
        _save_token(credentials)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Gmail OAuth callback failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Google authorization could not be completed. Check the OAuth "
                "redirect URI, Gmail API enablement, and client configuration."
            ),
        ) from exc

    connection.execute(
        """
        INSERT INTO email_sync_state (id, email_address, connected_at, last_error)
        VALUES (1, ?, ?, NULL)
        ON CONFLICT(id) DO UPDATE SET
            email_address = excluded.email_address,
            connected_at = excluded.connected_at,
            last_error = NULL
        """,
        (email_address, _utc_now()),
    )
    connection.commit()
    safe_email = html.escape(email_address)
    response = HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>JobPilot Gmail Connected</title></head>"
        "<body style='font-family:system-ui,sans-serif;max-width:640px;"
        "margin:10vh auto;padding:24px;line-height:1.6'>"
        "<h2>Gmail connected successfully</h2>"
        f"<p>JobPilot is connected to <strong>{safe_email}</strong>.</p>"
        "<p>Only read-only Gmail access was requested. Email bodies and attachments "
        "are not stored in the JobPilot database.</p>"
        "<p>You can close this tab and return to JobPilot.</p>"
        "</body></html>"
    )
    response.delete_cookie("jobpilot_gmail_oauth_state", path="/api/email/oauth")
    return response


def _service_for_credentials(credentials: Any) -> Any:
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Install google-api-python-client to use Gmail integration.",
        ) from exc
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


@router.post("/sync")
def sync_gmail(
    request: GmailSyncRequest,
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _ensure_email_schema(connection)
    service = _gmail_service()
    scanned = 0
    imported = 0
    duplicates = 0
    unclassified = 0
    errors = 0
    query = _gmail_query(request.days_back)

    sync_state = connection.execute(
        "SELECT next_page_token, sync_query_days_back FROM email_sync_state WHERE id = 1"
    ).fetchone()
    page_token: str | None = None
    if (
        sync_state
        and sync_state["sync_query_days_back"] == request.days_back
        and sync_state["next_page_token"]
    ):
        page_token = str(sync_state["next_page_token"])

    try:
        while scanned < request.max_messages:
            page_size = min(100, request.max_messages - scanned)
            list_args: dict[str, Any] = {
                "userId": "me",
                "q": query,
                "maxResults": page_size,
            }
            if page_token:
                list_args["pageToken"] = page_token

            try:
                listing = service.users().messages().list(**list_args).execute()
            except Exception:
                # Gmail page tokens can expire or become invalid as the mailbox
                # changes. Retry once from the newest page; dedupe is ID-based.
                if not page_token:
                    raise
                logger.info("Stored Gmail page token failed; restarting from the newest result page")
                page_token = None
                connection.execute(
                    "UPDATE email_sync_state SET next_page_token = NULL WHERE id = 1"
                )
                connection.commit()
                list_args.pop("pageToken", None)
                listing = service.users().messages().list(**list_args).execute()

            messages = listing.get("messages", []) or []
            if not messages:
                page_token = listing.get("nextPageToken")
                break

            for item in messages:
                if scanned >= request.max_messages:
                    break
                scanned += 1
                message_id = str(item.get("id", "")).strip()
                if not message_id:
                    errors += 1
                    continue
                exists = connection.execute(
                    "SELECT 1 FROM email_scanned_messages WHERE gmail_message_id = ?",
                    (message_id,),
                ).fetchone()
                if exists:
                    duplicates += 1
                    continue
                try:
                    message = service.users().messages().get(
                        userId="me",
                        id=message_id,
                        format="full",
                    ).execute()
                    outcome = _record_message(connection, message)
                    if outcome == "imported":
                        imported += 1
                    elif outcome == "duplicate":
                        duplicates += 1
                    elif outcome == "unclassified":
                        unclassified += 1
                    else:
                        errors += 1
                except Exception as exc:
                    errors += 1
                    logger.warning(
                        "Skipping Gmail message after retrieval/parse error (%s)",
                        type(exc).__name__,
                    )
            connection.commit()
            page_token = listing.get("nextPageToken")
            if not page_token:
                break
    except HTTPException:
        raise
    except Exception as exc:
        connection.rollback()
        logger.warning("Gmail sync failed: %s", type(exc).__name__)
        connection.execute(
            """
            INSERT INTO email_sync_state (id, last_error)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET last_error = excluded.last_error
            """,
            (f"Gmail sync failed ({type(exc).__name__}).",),
        )
        connection.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gmail sync failed. Check the connection and try again.",
        ) from exc

    now = _utc_now()
    connection.execute(
        """
        INSERT INTO email_sync_state (
            id, last_sync_at, last_sync_imported, last_sync_scanned,
            last_error, next_page_token, sync_query_days_back
        ) VALUES (1, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_sync_at = excluded.last_sync_at,
            last_sync_imported = excluded.last_sync_imported,
            last_sync_scanned = excluded.last_sync_scanned,
            last_error = NULL,
            next_page_token = excluded.next_page_token,
            sync_query_days_back = excluded.sync_query_days_back
        """,
        (now, imported, scanned, page_token, request.days_back),
    )
    connection.commit()
    return {
        "status": "completed",
        "query_days_back": request.days_back,
        "scanned": scanned,
        "imported": imported,
        "duplicates": duplicates,
        "unclassified": unclassified,
        "errors": errors,
        "review_required": imported,
        "more_pages_pending": bool(page_token),
        "full_email_bodies_stored": False,
        "note": (
            "Detected events remain pending until you approve or ignore them. "
            "If more pages remain, run Sync again to continue scanning older messages."
        ),
    }


@router.get("/events")
def list_email_events(
    review_status: str = Query(default="pending", pattern="^(pending|approved|ignored|all)$"),
    event_type: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _ensure_email_schema(connection)
    clauses: list[str] = []
    params: list[Any] = []
    if review_status != "all":
        clauses.append("e.review_status = ?")
        params.append(review_status)
    allowed_types = set(PROPOSED_STATUS_BY_EVENT)
    if event_type is not None:
        if event_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"event_type must be one of: {', '.join(sorted(allowed_types))}.",
            )
        clauses.append("e.event_type = ?")
        params.append(event_type)
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = connection.execute(
        f"SELECT COUNT(*) AS total FROM application_email_events e {where_clause}",
        params,
    ).fetchone()["total"]
    rows = connection.execute(
        _email_event_query(where_clause)
        + " ORDER BY COALESCE(e.received_at, e.created_at) DESC, e.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "items": [_event_dict(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _apply_proposed_status(
    connection: sqlite3.Connection,
    application_id: int,
    proposed_status: str,
) -> tuple[str, str]:
    application = connection.execute(
        "SELECT status, applied_at FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected tracked application was not found.",
        )

    current = str(application["status"])
    next_status = current
    if current not in TERMINAL_APPLICATION_STATUSES:
        if APPLICATION_STATUS_ORDER.get(proposed_status, -1) > APPLICATION_STATUS_ORDER.get(current, -1):
            next_status = proposed_status

    if next_status != current:
        applied_at = application["applied_at"]
        if next_status in {
            "applied", "assessment", "interview", "offer", "rejected", "withdrawn"
        } and not applied_at:
            applied_at = _utc_now()
        connection.execute(
            "UPDATE applications SET status = ?, applied_at = ?, updated_at = ? WHERE id = ?",
            (next_status, applied_at, _utc_now(), application_id),
        )
    return current, next_status


@router.post("/events/{event_id}/review")
def review_email_event(
    request: EmailEventReviewRequest,
    event_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _ensure_email_schema(connection)
    event = connection.execute(
        "SELECT * FROM application_email_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email event was not found.",
        )
    if event["review_status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email event has already been reviewed.",
        )

    now = _utc_now()
    if request.decision == "ignore":
        connection.execute(
            """
            UPDATE application_email_events
            SET review_status = 'ignored', review_note = ?, reviewed_at = ?
            WHERE id = ?
            """,
            (request.note, now, event_id),
        )
        connection.commit()
        return {"id": event_id, "review_status": "ignored", "application_status_changed": False}

    application_id = request.application_id or event["matched_application_id"]
    if application_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select the tracked application before approving this event.",
        )

    before_status, after_status = _apply_proposed_status(
        connection,
        int(application_id),
        str(event["proposed_status"]),
    )
    connection.execute(
        """
        UPDATE application_email_events
        SET review_status = 'approved',
            matched_application_id = ?,
            match_confidence = CASE WHEN ? THEN 1.0 ELSE match_confidence END,
            review_note = ?, before_status = ?, after_status = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (
            int(application_id),
            1 if request.application_id is not None else 0,
            request.note,
            before_status,
            after_status,
            now,
            event_id,
        ),
    )
    connection.commit()
    return {
        "id": event_id,
        "review_status": "approved",
        "application_id": int(application_id),
        "event_type": event["event_type"],
        "proposed_status": event["proposed_status"],
        "before_status": before_status,
        "after_status": after_status,
        "application_status_changed": before_status != after_status,
        "reviewed_at": now,
    }


@router.post("/disconnect")
def disconnect_gmail(
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _ensure_email_schema(connection)
    token_path = _token_path()
    try:
        if token_path.exists():
            token_path.unlink()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not remove the local Gmail token. Close processes using the file and retry.",
        ) from exc
    connection.execute(
        """
        INSERT INTO email_sync_state (id, email_address, connected_at, last_error)
        VALUES (1, NULL, NULL, NULL)
        ON CONFLICT(id) DO UPDATE SET
            email_address = NULL,
            connected_at = NULL,
            last_error = NULL
        """
    )
    connection.commit()
    return {
        "connected": False,
        "message": "Gmail disconnected. Previously imported event metadata was kept in JobPilot.",
    }
