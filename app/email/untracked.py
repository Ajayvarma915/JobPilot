"""Applications seen in your email that JobPilot is not tracking yet.

The Gmail sync only attaches a message to an application you already track. A confirmation such as
"We have received your application for the position Associate Engineer" for a job you never saved
(for example one you applied to through a friend's referral) used to be dropped silently. It is now
kept as a SUGGESTION: nothing is added to your tracker until you press Add, and you can correct the
company and role first. Only application-confirmation emails are suggested; no message body is stored.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path as ApiPath, Query, status
from pydantic import BaseModel, Field

from app.applications.tracker import get_application_db

router = APIRouter(prefix="/api/email/suggestions", tags=["email"])

# Mail sent on an employer's behalf by an applicant tracking system: the sender's own name is the company.
_ATS_DOMAINS = {
    "myworkday.com", "greenhouse-mail.io", "greenhouse.io", "lever.co", "hire.lever.co", "ashbyhq.com",
    "smartrecruiters.com", "icims.com", "successfactors.com", "taleo.net", "jobvite.com", "workable.com",
    "eightfold.ai", "oraclecloud.com", "recruitee.com", "breezy.hr",
}
_ROLE_PATTERNS = (
    re.compile(r"application (?:for|to) the (?:position|role|job|opening) (?:of )?(?P<t>.+?)(?:\s+-\s+[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)?\s*(?:\.|,| at |\n|$)", re.IGNORECASE),
    re.compile(r"application for (?:the )?(?P<t>[A-Z][^\n.]{3,80}?)(?:\s+-\s+[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)?\s*(?:\.|,| at |\n|$)"),
    re.compile(r"thank you for applying to (?:the )?(?P<t>[^\n.]{3,80}?) (?:position|role)", re.IGNORECASE),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS email_application_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT NOT NULL UNIQUE,
            company_guess TEXT NOT NULL DEFAULT '',
            title_guess TEXT NOT NULL DEFAULT '',
            subject TEXT NOT NULL DEFAULT '',
            sender TEXT NOT NULL DEFAULT '',
            received_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'added', 'dismissed')),
            application_id INTEGER,
            created_at TEXT NOT NULL
        )
        """
    )


def guess_company(sender: str) -> str:
    """Best-effort company name from the sender (an ATS address like qualcomm@myworkday.com)."""
    sender = sender.strip()
    if "<" in sender:
        display, _, address = sender.partition("<")
        display, email = display.strip().strip('"'), address.rstrip("> ").strip()
    else:
        display, email = "", sender  # a bare address has no display name
    local, _, domain = email.partition("@")
    domain = domain.lower().strip()
    registered = ".".join(domain.split(".")[-2:]) if domain else ""
    generic = r"(no[-_ ]?reply|noreply|careers?|jobs?|talent|recruiting|recruitment|hr|mailer|notifications?|team)"
    if registered in _ATS_DOMAINS or domain in _ATS_DOMAINS:
        # an ATS sends for many companies: its own name is the company unless the sender is generic
        label = display if (re.fullmatch(generic, local, re.IGNORECASE) and display) else local
    elif display and not re.fullmatch(generic, display, re.IGNORECASE) and "@" not in display:
        label = display
    else:
        parts = domain.split(".")
        label = parts[-2] if len(parts) >= 2 else local
    label = re.sub(r"(?i)\b(no[-_ ]?reply|careers?|jobs?|talent|recruiting|recruitment|team)\b", "", label)
    label = re.sub(r"[-_.@]+", " ", label).strip()
    return label.title() if label.islower() else label


_COMPANY_IN_TEXT = re.compile(
    r"(?:thank(?:s| you) for applying (?:to|at|with)|application (?:to|with)|applying (?:to|at)) (?:the )?"
    r"(?P<c>[A-Z][A-Za-z0-9&.' -]{1,40}?)(?=[!.,\n]| for | - | as | team|$)"
)


def best_company(sender: str, subject: str, snippet: str, body_text: str) -> str:
    """The company named in the message itself ("Thank you for applying to Coinbase") if there is one,
    otherwise the one the sender suggests."""
    for text in (subject, snippet, body_text):
        found = _COMPANY_IN_TEXT.search(re.sub(r"[ \t]+", " ", text or ""))
        if found:
            name = found.group("c").strip(" -.")
            # "...applying to the Platform Engineer role at Initech" names a job, not a company
            if not re.search(r"(?i)\b(role|position|job|opening|opportunity|team|at)\b", name):
                return name
    return guess_company(sender)


def guess_title(subject: str, snippet: str, body_text: str) -> str:
    for text in (body_text, snippet, subject):
        flat = re.sub(r"[ \t]+", " ", text or "")
        for pattern in _ROLE_PATTERNS:
            found = pattern.search(flat)
            if found:
                title = found.group("t").strip(" -:\"'")
                if 3 <= len(title) <= 120:
                    return title
    return ""


def record_suggestion(connection: sqlite3.Connection, *, message_id: str, received_at: str | None, sender: str, subject: str,
                      snippet: str, body_text: str) -> None:
    ensure_table(connection)
    connection.execute(
        """
        INSERT OR IGNORE INTO email_application_suggestions
            (gmail_message_id, company_guess, title_guess, subject, sender, received_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (message_id, best_company(sender, subject, snippet, body_text)[:255], guess_title(subject, snippet, body_text)[:255], subject[:300], sender[:300],
         received_at, _utc_now()),
    )


def _insert(connection: sqlite3.Connection, table: str, values: dict[str, Any]) -> int:
    """Insert only the columns this database has (older databases lack some optional ones)."""
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    kept = {key: value for key, value in values.items() if key in columns}
    names = ", ".join(kept)
    cursor = connection.execute(f"INSERT INTO {table} ({names}) VALUES ({', '.join('?' * len(kept))})", tuple(kept.values()))
    return int(cursor.lastrowid)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


@router.get("")
def list_suggestions(
    review_status: str = Query("pending", pattern="^(pending|added|dismissed|all)$"),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    ensure_table(connection)
    where, params = ("", ()) if review_status == "all" else ("WHERE status = ?", (review_status,))
    rows = connection.execute(
        f"SELECT * FROM email_application_suggestions {where} ORDER BY COALESCE(received_at, created_at) DESC LIMIT 200", params
    ).fetchall()
    items = []
    for row in rows:
        item = _row(row)
        if not item["company_guess"] or "@" in item["company_guess"]:  # a guess made by an older version
            item["company_guess"] = best_company(item["sender"], item["subject"], "", "")
        # If you already track a job at this company, this email may simply be its confirmation.
        try:
            titles = connection.execute(
                """
                SELECT j.title FROM applications a JOIN jobs j ON j.id = a.job_id JOIN companies c ON c.id = j.company_id
                WHERE lower(c.name) = lower(?) ORDER BY a.id
                """,
                (item["company_guess"],),
            ).fetchall()
        except sqlite3.OperationalError:
            titles = []
        item["already_tracked_titles"] = [r[0] for r in titles]
        items.append(item)
    return {"items": items}


class AddSuggestion(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    url: str | None = Field(default=None, max_length=1000)


@router.post("/{suggestion_id}/add", status_code=status.HTTP_201_CREATED)
def add_suggestion(
    request: AddSuggestion,
    suggestion_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    """Track this application as Applied (you confirm the company and role first)."""
    ensure_table(connection)
    suggestion = connection.execute("SELECT * FROM email_application_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="Suggestion not found.")
    if suggestion["status"] == "added":
        raise HTTPException(status_code=409, detail="This application was already added to your tracker.")

    now = _utc_now()
    company_name, title = request.company.strip(), request.title.strip()
    company = connection.execute("SELECT id FROM companies WHERE name = ? COLLATE NOCASE", (company_name,)).fetchone()
    if company is None:
        company_id = _insert(connection, "companies", {"name": company_name, "source_type": "email", "created_at": now})
    else:
        company_id = int(company["id"])

    external_id = f"email-{suggestion['gmail_message_id']}"
    url = (request.url or "").strip() or f"https://mail.google.com/mail/u/0/#all/{suggestion['gmail_message_id']}"
    job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "external_id" in job_columns:
        job = connection.execute("SELECT id FROM jobs WHERE source = 'email_application' AND external_id = ?", (external_id,)).fetchone()
    else:
        job = connection.execute("SELECT id FROM jobs WHERE source = 'email_application' AND url = ?", (url,)).fetchone()
    if job is None:
        job_id = _insert(connection, "jobs", {
            "company_id": company_id, "external_id": external_id, "title": title, "location": None, "url": url,
            "description": "Added from an application confirmation email. Open the original email for the posting details.",
            "source": "email_application", "first_seen_at": now, "last_seen_at": now, "is_active": 1,
            "created_at": now, "updated_at": now,  # NOT NULL in the real jobs table
        })
    else:
        job_id = int(job["id"])
    if connection.execute("SELECT 1 FROM applications WHERE job_id = ?", (job_id,)).fetchone():
        raise HTTPException(status_code=409, detail="This job is already tracked.")

    applied_at = suggestion["received_at"] or now
    application_id = _insert(connection, "applications", {
        "job_id": job_id, "status": "applied", "applied_at": applied_at, "created_at": now, "updated_at": now,
        "notes": "Added from your confirmation email (you confirmed the company and role).",
    })
    connection.execute(
        "UPDATE email_application_suggestions SET status = 'added', application_id = ? WHERE id = ?", (application_id, suggestion_id)
    )
    connection.commit()
    return {"suggestion_id": suggestion_id, "application_id": application_id, "job_id": job_id, "status": "applied"}


@router.post("/{suggestion_id}/dismiss")
def dismiss_suggestion(
    suggestion_id: int = ApiPath(ge=1), connection: sqlite3.Connection = Depends(get_application_db)
) -> dict[str, Any]:
    ensure_table(connection)
    cursor = connection.execute(
        "UPDATE email_application_suggestions SET status = 'dismissed' WHERE id = ? AND status = 'pending'", (suggestion_id,)
    )
    connection.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="No pending suggestion with that id.")
    return {"suggestion_id": suggestion_id, "status": "dismissed"}
