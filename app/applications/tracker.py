from __future__ import annotations

import os
import json
import re
import sqlite3
from collections.abc import Generator
from datetime import date, datetime, timezone
from pathlib import Path, PurePath
from urllib.parse import urlsplit
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path as ApiPath,
    Query,
    status,
)
from pydantic import BaseModel, Field, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_RESUMES_DIR = PROJECT_ROOT / "data" / "generated_resumes"

ApplicationStatus = Literal[
    "saved",
    "preparing",
    "ready_to_apply",
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
]

ALL_STATUSES = (
    "saved",
    "preparing",
    "ready_to_apply",
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
)

APPLIED_OR_LATER_STATUSES = {
    "applied",
    "assessment",
    "interview",
    "offer",
    "rejected",
    "withdrawn",
}

router = APIRouter(
    prefix="/api/applications",
    tags=["applications"],
)


def _validate_generated_filename(value: str | None) -> str | None:
    """Accept only an existing generated PDF or DOCX filename."""
    if value is None:
        return None

    candidate = PurePath(value)

    if (
        "/" in value
        or "\\" in value
        or candidate.name != value
        or candidate.suffix.lower() not in {".pdf", ".docx"}
    ):
        raise ValueError(
            "Use only a generated PDF or DOCX filename, not a path."
        )

    generated_path = (GENERATED_RESUMES_DIR / value).resolve()

    if (
        generated_path.parent != GENERATED_RESUMES_DIR.resolve()
        or not generated_path.is_file()
    ):
        raise ValueError(
            "The referenced generated resume file does not exist."
        )

    return value


class ApplicationCreate(BaseModel):
    job_id: int = Field(gt=0)
    status: ApplicationStatus = "saved"
    notes: str | None = Field(default=None, max_length=5000)
    resume_filename: str | None = Field(default=None, max_length=255)
    cover_letter_filename: str | None = Field(default=None, max_length=255)
    next_action: str | None = Field(default=None, max_length=500)
    follow_up_date: date | None = None

    @field_validator("resume_filename", "cover_letter_filename")
    @classmethod
    def validate_generated_filename(
        cls,
        value: str | None,
    ) -> str | None:
        return _validate_generated_filename(value)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    notes: str | None = Field(default=None, max_length=5000)
    resume_filename: str | None = Field(default=None, max_length=255)
    cover_letter_filename: str | None = Field(default=None, max_length=255)
    next_action: str | None = Field(default=None, max_length=500)
    follow_up_date: date | None = None
    job_reviewed: bool | None = None
    eligibility_confirmed: bool | None = None
    resume_reviewed: bool | None = None
    application_details_reviewed: bool | None = None

    @field_validator("status")
    @classmethod
    def validate_status_not_null(
        cls,
        value: ApplicationStatus | None,
    ) -> ApplicationStatus:
        if value is None:
            raise ValueError(
                "Status cannot be null; omit it to leave status unchanged."
            )
        return value

    @field_validator(
        "job_reviewed",
        "eligibility_confirmed",
        "resume_reviewed",
        "application_details_reviewed",
    )
    @classmethod
    def validate_review_flags_not_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("Review confirmations cannot be null.")
        return value

    @field_validator("resume_filename", "cover_letter_filename")
    @classmethod
    def validate_generated_filename(
        cls,
        value: str | None,
    ) -> str | None:
        return _validate_generated_filename(value)


class ApplicationCustomQuestion(BaseModel):
    question: str = Field(default="", max_length=500)
    answer: str = Field(default="", max_length=6000)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        cleaned = value.strip()
        return cleaned


class ApplicationPreparationUpdate(BaseModel):
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    current_location: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    current_employer: str | None = Field(default=None, max_length=200)
    current_title: str | None = Field(default=None, max_length=200)
    years_experience: str | None = Field(default=None, max_length=100)
    notice_period: str | None = Field(default=None, max_length=120)
    work_authorization: str | None = Field(default=None, max_length=240)
    requires_sponsorship: Literal["yes", "no", "unknown"] | None = None
    salary_expectation: str | None = Field(default=None, max_length=200)
    cover_letter_draft: str | None = Field(default=None, max_length=16000)
    custom_questions: list[ApplicationCustomQuestion] | None = Field(default=None, max_length=15)
    resume_filename: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        if cleaned and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
            raise ValueError("Enter a valid email address.")
        return cleaned or None

    @field_validator("linkedin_url", "github_url", "portfolio_url")
    @classmethod
    def validate_profile_urls(cls, value: str | None) -> str | None:
        cleaned = (value or "").strip()
        if not cleaned:
            return None
        parts = urlsplit(cleaned)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Profile links must be valid HTTP(S) URLs.")
        return cleaned

    @field_validator("resume_filename")
    @classmethod
    def validate_resume_filename(cls, value: str | None) -> str | None:
        return _validate_generated_filename(value)


def _database_path() -> Path:
    configured = os.getenv("JOBPILOT_DATABASE_PATH")

    if configured:
        return Path(configured).expanduser().resolve()

    return PROJECT_ROOT / "jobpilot.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_schema(connection: sqlite3.Connection) -> None:
    """Create only the tracker table; preserve existing jobs and companies."""
    existing = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    if "jobs" not in existing or "companies" not in existing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "JobPilot jobs database is not initialized. "
                "Restore the job database before using the Applications tracker."
            ),
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'saved'
                CHECK (status IN (
                    'saved',
                    'preparing',
                    'ready_to_apply',
                    'applied',
                    'assessment',
                    'interview',
                    'offer',
                    'rejected',
                    'withdrawn'
                )),
            notes TEXT,
            resume_filename TEXT,
            cover_letter_filename TEXT,
            applied_at TEXT,
            next_action TEXT,
            follow_up_date TEXT,
            job_reviewed INTEGER NOT NULL DEFAULT 0,
            eligibility_confirmed INTEGER NOT NULL DEFAULT 0,
            resume_reviewed INTEGER NOT NULL DEFAULT 0,
            application_details_reviewed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id)
                REFERENCES jobs(id)
                ON DELETE CASCADE
        )
        """
    )

    # Safe, additive migration for installations that created the table before
    # the application-readiness workflow existed.
    existing_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(applications)"
        ).fetchall()
    }
    review_columns = {
        "job_reviewed": "INTEGER NOT NULL DEFAULT 0",
        "eligibility_confirmed": "INTEGER NOT NULL DEFAULT 0",
        "resume_reviewed": "INTEGER NOT NULL DEFAULT 0",
        "application_details_reviewed": "INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, column_definition in review_columns.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE applications ADD COLUMN {column_name} {column_definition}"
            )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS application_preparations (
            application_id INTEGER PRIMARY KEY,
            contact_name TEXT,
            email TEXT,
            phone TEXT,
            current_location TEXT,
            linkedin_url TEXT,
            github_url TEXT,
            portfolio_url TEXT,
            current_employer TEXT,
            current_title TEXT,
            years_experience TEXT,
            notice_period TEXT,
            work_authorization TEXT,
            requires_sponsorship TEXT CHECK (
                requires_sponsorship IS NULL OR requires_sponsorship IN ('yes', 'no', 'unknown')
            ),
            salary_expectation TEXT,
            cover_letter_draft TEXT,
            custom_questions_json TEXT NOT NULL DEFAULT '[]',
            prepared_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(application_id)
                REFERENCES applications(id)
                ON DELETE CASCADE
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_status
        ON applications(status)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_applications_follow_up_date
        ON applications(follow_up_date)
        """
    )

    connection.commit()


def get_application_db() -> Generator[sqlite3.Connection, None, None]:
    database_path = _database_path()

    if not database_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"JobPilot database was not found at {database_path}.",
        )

    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(
            str(database_path),
            timeout=10,
            # FastAPI may enter/exit a synchronous dependency on different
            # worker threads. This connection is request-scoped and is never
            # shared between requests, so cross-thread hand-off is safe.
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        _ensure_schema(connection)
        yield connection

    except sqlite3.OperationalError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Applications database is unavailable: {exc}",
        ) from exc

    finally:
        if connection is not None:
            connection.close()


def _application_query(where_sql: str = "") -> str:
    return f"""
        SELECT
            a.id,
            a.job_id,
            a.status,
            a.notes,
            a.resume_filename,
            a.cover_letter_filename,
            a.applied_at,
            a.next_action,
            a.follow_up_date,
            a.job_reviewed,
            a.eligibility_confirmed,
            a.resume_reviewed,
            a.application_details_reviewed,
            a.created_at,
            a.updated_at,
            j.title AS job_title,
            j.location AS job_location,
            j.url AS job_url,
            j.source AS job_source,
            j.is_active AS job_is_active,
            c.name AS company_name
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN companies c ON c.id = j.company_id
        {where_sql}
    """


def _serialize(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "job_id": row["job_id"],
        "status": row["status"],
        "notes": row["notes"],
        "resume_filename": row["resume_filename"],
        "cover_letter_filename": row["cover_letter_filename"],
        "applied_at": row["applied_at"],
        "next_action": row["next_action"],
        "follow_up_date": row["follow_up_date"],
        "job_reviewed": bool(row["job_reviewed"]),
        "eligibility_confirmed": bool(row["eligibility_confirmed"]),
        "resume_reviewed": bool(row["resume_reviewed"]),
        "application_details_reviewed": bool(row["application_details_reviewed"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "job": {
            "id": row["job_id"],
            "title": row["job_title"],
            "company": row["company_name"],
            "location": row["job_location"],
            "url": row["job_url"],
            "source": row["job_source"],
            "is_active": bool(row["job_is_active"]),
        },
    }


def _load_application(
    connection: sqlite3.Connection,
    application_id: int,
) -> dict[str, Any] | None:
    row = connection.execute(
        _application_query("WHERE a.id = ?"),
        (application_id,),
    ).fetchone()

    return _serialize(row) if row else None


def _validate_job_exists(
    connection: sqlite3.Connection,
    job_id: int,
) -> None:
    row = connection.execute(
        "SELECT id FROM jobs WHERE id = ?",
        (job_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} was not found.",
        )


@router.get("/stats")
def get_application_stats(
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS total
        FROM applications
        GROUP BY status
        """
    ).fetchall()

    counts = {key: 0 for key in ALL_STATUSES}

    for row in rows:
        counts[row["status"]] = row["total"]

    total = sum(counts.values())

    needs_action = sum(
        counts[key]
        for key in ("saved", "preparing", "ready_to_apply")
    )

    return {
        "total": total,
        "needs_action": needs_action,
        "by_status": counts,
    }


@router.get("")
def list_applications(
    status_filter: ApplicationStatus | None = Query(
        default=None,
        alias="status",
    ),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    clauses: list[str] = []
    parameters: list[Any] = []

    if status_filter:
        clauses.append("a.status = ?")
        parameters.append(status_filter)

    if q and q.strip():
        clauses.append(
            """
            (
                j.title LIKE ?
                OR c.name LIKE ?
                OR COALESCE(a.notes, '') LIKE ?
            )
            """
        )

        needle = f"%{q.strip()}%"
        parameters.extend([needle, needle, needle])

    where_sql = (
        f"WHERE {' AND '.join(clauses)}"
        if clauses
        else ""
    )

    total_row = connection.execute(
        f"""
        SELECT COUNT(*) AS total
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN companies c ON c.id = j.company_id
        {where_sql}
        """,
        parameters,
    ).fetchone()

    rows = connection.execute(
        _application_query(where_sql)
        + """
        ORDER BY a.updated_at DESC, a.id DESC
        LIMIT ? OFFSET ?
        """,
        [*parameters, limit, offset],
    ).fetchall()

    return {
        "items": [_serialize(row) for row in rows],
        "total": total_row["total"],
        "limit": limit,
        "offset": offset,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    request: ApplicationCreate,
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    _validate_job_exists(connection, request.job_id)

    existing = connection.execute(
        "SELECT id FROM applications WHERE job_id = ?",
        (request.job_id,),
    ).fetchone()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This job is already tracked as "
                f"application {existing['id']}."
            ),
        )

    now = _utc_now()

    applied_at = (
        now
        if request.status in APPLIED_OR_LATER_STATUSES
        else None
    )

    try:
        cursor = connection.execute(
            """
            INSERT INTO applications (
                job_id,
                status,
                notes,
                resume_filename,
                cover_letter_filename,
                applied_at,
                next_action,
                follow_up_date,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request.job_id,
                request.status,
                request.notes,
                request.resume_filename,
                request.cover_letter_filename,
                applied_at,
                request.next_action,
                (
                    request.follow_up_date.isoformat()
                    if request.follow_up_date
                    else None
                ),
                now,
                now,
            ),
        )

        connection.commit()

    except sqlite3.IntegrityError as exc:
        connection.rollback()

        if "UNIQUE constraint failed" in str(exc):
            raise HTTPException(
                status_code=409,
                detail="This job is already tracked.",
            ) from exc

        raise HTTPException(
            status_code=422,
            detail="The application could not be saved.",
        ) from exc

    result = _load_application(
        connection,
        int(cursor.lastrowid),
    )

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="The saved application could not be loaded.",
        )

    return result


@router.get("/tracked-job-ids")
def list_tracked_job_ids(
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, list[int]]:
    """Return every tracked job ID, independent of the paged UI list."""
    rows = connection.execute(
        "SELECT job_id FROM applications ORDER BY job_id"
    ).fetchall()
    return {"job_ids": [int(row["job_id"]) for row in rows]}


@router.get("/by-job/{job_id}")
def get_application_for_job(
    job_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    """Find a tracked record even when it isn't on the current UI page."""
    row = connection.execute(
        _application_query("WHERE a.job_id = ?"),
        (job_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="This job is not currently tracked.",
        )

    return _serialize(row)


def _available_resume_files() -> list[dict[str, Any]]:
    """Return generated resume files only; never expose arbitrary file paths."""
    if not GENERATED_RESUMES_DIR.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for path in GENERATED_RESUMES_DIR.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".pdf", ".docx"}:
            continue
        try:
            modified_at = datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat(timespec="seconds")
        except OSError:
            continue
        results.append(
            {
                "filename": path.name,
                "format": path.suffix.lower().lstrip("."),
                "modified_at": modified_at,
                "size_bytes": path.stat().st_size,
            }
        )

    results.sort(key=lambda item: item["modified_at"], reverse=True)
    return results[:100]


def _assess_readiness(
    *,
    job_is_active: bool,
    job_url: str | None,
    job_description: str | None,
    resume_filename: str | None,
    job_reviewed: bool,
    eligibility_confirmed: bool,
    resume_reviewed: bool,
    application_details_reviewed: bool,
) -> dict[str, Any]:
    parts = urlsplit(job_url or "")
    url_is_valid = parts.scheme in {"http", "https"} and bool(parts.netloc)
    description_is_available = len((job_description or "").strip()) >= 100

    resume_path: Path | None = None
    if resume_filename:
        try:
            candidate = (GENERATED_RESUMES_DIR / resume_filename).resolve()
            if (
                candidate.parent == GENERATED_RESUMES_DIR.resolve()
                and candidate.is_file()
                and candidate.suffix.lower() in {".pdf", ".docx"}
            ):
                resume_path = candidate
        except OSError:
            resume_path = None

    resume_exists = resume_path is not None
    resume_is_pdf = bool(resume_path and resume_path.suffix.lower() == ".pdf")

    checks = [
        {
            "id": "job_active",
            "label": "Listing is marked active in JobPilot",
            "passed": bool(job_is_active),
            "blocking": True,
            "detail": (
                "The local listing is marked active. Open the employer page to confirm it is still accepting applications."
                if job_is_active
                else "The listing is marked inactive in JobPilot. Recheck the employer posting before proceeding."
            ),
        },
        {
            "id": "posting_url",
            "label": "Original posting link is valid",
            "passed": url_is_valid,
            "blocking": True,
            "detail": (
                "An HTTP(S) job posting link is available."
                if url_is_valid
                else "No valid HTTP(S) application link is saved for this job."
            ),
        },
        {
            "id": "job_description",
            "label": "Full job description is available",
            "passed": description_is_available,
            "blocking": True,
            "detail": (
                "JobPilot has enough description text to review role requirements."
                if description_is_available
                else "The saved description is missing or too short. Open the employer posting and verify its requirements."
            ),
        },
        {
            "id": "job_reviewed",
            "label": "Job responsibilities and requirements reviewed",
            "passed": job_reviewed,
            "blocking": True,
            "detail": "Confirm that you reviewed the actual posting, responsibilities, and required qualifications.",
        },
        {
            "id": "eligibility_confirmed",
            "label": "Location and eligibility confirmed",
            "passed": eligibility_confirmed,
            "blocking": True,
            "detail": "Confirm your work-location eligibility, experience, education, and any required work authorization.",
        },
        {
            "id": "resume_selected",
            "label": "Generated tailored resume selected",
            "passed": resume_exists,
            "blocking": True,
            "detail": (
                f"Selected file: {resume_filename}."
                if resume_exists
                else "Generate and select a tailored PDF or DOCX from Resume Studio."
            ),
        },
        {
            "id": "resume_reviewed",
            "label": "Resume content reviewed",
            "passed": resume_reviewed,
            "blocking": True,
            "detail": "Review the downloaded document for accuracy, layout, and claims before using it.",
        },
        {
            "id": "application_details_reviewed",
            "label": "Application-form details prepared",
            "passed": application_details_reviewed,
            "blocking": True,
            "detail": "Confirm you can answer employer form questions accurately and provide any required links or documents.",
        },
        {
            "id": "pdf_preferred",
            "label": "PDF format preferred for upload",
            "passed": resume_is_pdf,
            "blocking": False,
            "detail": (
                "PDF is selected, which generally preserves layout. Follow the employer's requested file format."
                if resume_is_pdf
                else "A DOCX is selected. PDF is often convenient, but follow the employer's requested format."
            ),
        },
    ]

    blocking_checks = [check for check in checks if check["blocking"]]
    blockers = [check["label"] for check in blocking_checks if not check["passed"]]

    return {
        "ready": not blockers,
        "readiness_label": "Ready for your review" if not blockers else "More review required",
        "completed_checks": sum(1 for check in checks if check["passed"]),
        "total_checks": len(checks),
        "checks": checks,
        "blockers": blockers,
        "review": {
            "job_reviewed": bool(job_reviewed),
            "eligibility_confirmed": bool(eligibility_confirmed),
            "resume_reviewed": bool(resume_reviewed),
            "application_details_reviewed": bool(application_details_reviewed),
        },
        "resume_options": _available_resume_files(),
        "submission_note": "JobPilot prepares and checks your application. It does not submit the employer form automatically.",
    }


@router.get("/{application_id}/readiness")
def get_application_readiness(
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
            a.id,
            a.status,
            a.resume_filename,
            a.job_reviewed,
            a.eligibility_confirmed,
            a.resume_reviewed,
            a.application_details_reviewed,
            j.is_active AS job_is_active,
            j.url AS job_url,
            j.description AS job_description,
            j.title AS job_title,
            c.name AS company_name
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN companies c ON c.id = j.company_id
        WHERE a.id = ?
        """,
        (application_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Application was not found.")

    result = _assess_readiness(
        job_is_active=bool(row["job_is_active"]),
        job_url=row["job_url"],
        job_description=row["job_description"],
        resume_filename=row["resume_filename"],
        job_reviewed=bool(row["job_reviewed"]),
        eligibility_confirmed=bool(row["eligibility_confirmed"]),
        resume_reviewed=bool(row["resume_reviewed"]),
        application_details_reviewed=bool(row["application_details_reviewed"]),
    )
    result.update(
        {
            "application_id": int(row["id"]),
            "status": row["status"],
            "job": {
                "title": row["job_title"],
                "company": row["company_name"],
            },
            "resume_filename": row["resume_filename"],
        }
    )
    return result


def _preparation_blockers(
    *,
    contact_name: str | None,
    email: str | None,
    phone: str | None,
    current_location: str | None,
    resume_filename: str | None,
    job_is_active: bool,
    job_url: str | None,
    custom_questions: list[dict[str, str]],
) -> list[str]:
    blockers: list[str] = []
    if not (contact_name or "").strip():
        blockers.append("Add your full name.")
    if not (email or "").strip():
        blockers.append("Add your email address.")
    if not (phone or "").strip():
        blockers.append("Add your phone number.")
    if not (current_location or "").strip():
        blockers.append("Add your current location.")

    resume_exists = False
    if resume_filename:
        resume_exists = any(
            item["filename"] == resume_filename
            for item in _available_resume_files()
        )
    if not resume_exists:
        blockers.append("Select an existing generated PDF or DOCX resume.")

    parts = urlsplit(job_url or "")
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        blockers.append("The original job posting link is missing or invalid.")
    if not job_is_active:
        blockers.append("The job is marked inactive; verify the employer posting before proceeding.")

    for index, item in enumerate(custom_questions, start=1):
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        if question and not answer:
            blockers.append(f"Answer custom employer question {index} or remove it.")
        elif answer and not question:
            blockers.append(f"Add the prompt for custom employer answer {index}.")

    return blockers


def _preparation_response(
    connection: sqlite3.Connection,
    application_id: int,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT
            a.id AS application_id,
            a.status AS application_status,
            a.resume_filename,
            a.cover_letter_filename,
            j.id AS job_id,
            j.title AS job_title,
            j.location AS job_location,
            j.url AS job_url,
            j.description AS job_description,
            j.is_active AS job_is_active,
            c.name AS company_name,
            p.contact_name,
            p.email,
            p.phone,
            p.current_location,
            p.linkedin_url,
            p.github_url,
            p.portfolio_url,
            p.current_employer,
            p.current_title,
            p.years_experience,
            p.notice_period,
            p.work_authorization,
            p.requires_sponsorship,
            p.salary_expectation,
            p.cover_letter_draft,
            p.custom_questions_json,
            p.prepared_at,
            p.updated_at AS preparation_updated_at
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        JOIN companies c ON c.id = j.company_id
        LEFT JOIN application_preparations p ON p.application_id = a.id
        WHERE a.id = ?
        """,
        (application_id,),
    ).fetchone()
    if row is None:
        return None

    try:
        questions = json.loads(row["custom_questions_json"] or "[]")
        if not isinstance(questions, list):
            questions = []
    except (TypeError, json.JSONDecodeError):
        questions = []

    profile_fields = (
        "contact_name", "email", "phone", "current_location", "linkedin_url",
        "github_url", "portfolio_url", "current_employer", "current_title",
        "years_experience", "notice_period", "work_authorization",
        "requires_sponsorship", "salary_expectation",
    )
    profile = {field: row[field] for field in profile_fields}
    blockers = _preparation_blockers(
        contact_name=row["contact_name"],
        email=row["email"],
        phone=row["phone"],
        current_location=row["current_location"],
        resume_filename=row["resume_filename"],
        job_is_active=bool(row["job_is_active"]),
        job_url=row["job_url"],
        custom_questions=questions,
    )

    return {
        "application_id": int(row["application_id"]),
        "application_status": row["application_status"],
        "resume_filename": row["resume_filename"],
        "cover_letter_filename": row["cover_letter_filename"],
        "profile": profile,
        "cover_letter_draft": row["cover_letter_draft"] or "",
        "custom_questions": questions,
        "prepared": not blockers,
        "blockers": blockers,
        "resume_options": _available_resume_files(),
        "prepared_at": row["prepared_at"],
        "updated_at": row["preparation_updated_at"],
        "job": {
            "id": int(row["job_id"]),
            "title": row["job_title"],
            "company": row["company_name"],
            "location": row["job_location"],
            "url": row["job_url"],
            "description_available": len((row["job_description"] or "").strip()) >= 100,
            "is_active": bool(row["job_is_active"]),
        },
        "submission_note": "This is a copy-ready preparation workspace. It does not autofill or submit the employer's website.",
    }


@router.get("/{application_id}/preparation")
def get_application_preparation(
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Application was not found.")

    now = _utc_now()
    connection.execute(
        """
        INSERT OR IGNORE INTO application_preparations (
            application_id, created_at, updated_at
        ) VALUES (?, ?, ?)
        """,
        (application_id, now, now),
    )
    connection.commit()
    result = _preparation_response(connection, application_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Preparation data could not be loaded.")
    return result


@router.patch("/{application_id}/preparation")
def update_application_preparation(
    request: ApplicationPreparationUpdate,
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT id FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Application was not found.")

    changes = request.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one preparation field to save.")

    now = _utc_now()
    connection.execute(
        """
        INSERT OR IGNORE INTO application_preparations (
            application_id, created_at, updated_at
        ) VALUES (?, ?, ?)
        """,
        (application_id, now, now),
    )

    prep_columns = {
        "contact_name", "email", "phone", "current_location", "linkedin_url",
        "github_url", "portfolio_url", "current_employer", "current_title",
        "years_experience", "notice_period", "work_authorization",
        "requires_sponsorship", "salary_expectation", "cover_letter_draft",
        "custom_questions",
    }
    assignments: list[str] = []
    values: list[Any] = []

    if "resume_filename" in changes:
        connection.execute(
            "UPDATE applications SET resume_filename = ?, updated_at = ? WHERE id = ?",
            (changes.pop("resume_filename"), now, application_id),
        )

    for field, value in changes.items():
        if field not in prep_columns:
            continue
        if isinstance(value, str):
            value = value.strip()
        if field == "custom_questions":
            value = json.dumps(
                [item.model_dump() if isinstance(item, BaseModel) else item for item in (value or [])],
                ensure_ascii=False,
            )
            field = "custom_questions_json"
        assignments.append(f"{field} = ?")
        values.append(value)

    assignments.extend(["updated_at = ?", "prepared_at = NULL"])
    values.extend([now, application_id])
    connection.execute(
        f"UPDATE application_preparations SET {', '.join(assignments)} WHERE application_id = ?",
        values,
    )
    connection.commit()

    result = _preparation_response(connection, application_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Saved preparation data could not be loaded.")

    if result["prepared"]:
        connection.execute(
            "UPDATE application_preparations SET prepared_at = ? WHERE application_id = ?",
            (_utc_now(), application_id),
        )
        connection.commit()
        result = _preparation_response(connection, application_id) or result
    return result


@router.get("/{application_id}")
def get_application(
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    result = _load_application(connection, application_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Application was not found.",
        )

    return result


@router.patch("/{application_id}")
def update_application(
    request: ApplicationUpdate,
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    current = connection.execute(
        """
        SELECT
            a.id,
            a.status,
            a.applied_at,
            a.resume_filename,
            a.job_reviewed,
            a.eligibility_confirmed,
            a.resume_reviewed,
            a.application_details_reviewed,
            j.is_active AS job_is_active,
            j.url AS job_url,
            j.description AS job_description
        FROM applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.id = ?
        """,
        (application_id,),
    ).fetchone()

    if current is None:
        raise HTTPException(
            status_code=404,
            detail="Application was not found.",
        )

    changes = request.model_dump(exclude_unset=True)

    if not changes:
        raise HTTPException(
            status_code=422,
            detail="Provide at least one field to update.",
        )

    assignments: list[str] = []
    values: list[Any] = []

    allowed_fields = (
        "status",
        "notes",
        "resume_filename",
        "cover_letter_filename",
        "next_action",
        "follow_up_date",
        "job_reviewed",
        "eligibility_confirmed",
        "resume_reviewed",
        "application_details_reviewed",
    )

    for field in allowed_fields:
        if field not in changes:
            continue

        value = changes[field]

        if field == "follow_up_date":
            value = value.isoformat() if value else None
        elif field in {
            "job_reviewed",
            "eligibility_confirmed",
            "resume_reviewed",
            "application_details_reviewed",
        }:
            value = int(bool(value))

        assignments.append(f"{field} = ?")
        values.append(value)

    new_status = changes.get("status")

    if new_status == "ready_to_apply":
        prospective = {
            "job_is_active": bool(current["job_is_active"]),
            "job_url": current["job_url"],
            "job_description": current["job_description"],
            "resume_filename": changes.get(
                "resume_filename", current["resume_filename"]
            ),
            "job_reviewed": bool(changes.get("job_reviewed", current["job_reviewed"])),
            "eligibility_confirmed": bool(
                changes.get("eligibility_confirmed", current["eligibility_confirmed"])
            ),
            "resume_reviewed": bool(changes.get("resume_reviewed", current["resume_reviewed"])),
            "application_details_reviewed": bool(
                changes.get(
                    "application_details_reviewed",
                    current["application_details_reviewed"],
                )
            ),
        }
        readiness = _assess_readiness(
            job_is_active=prospective["job_is_active"],
            job_url=prospective["job_url"],
            job_description=prospective["job_description"],
            resume_filename=prospective["resume_filename"],
            job_reviewed=prospective["job_reviewed"],
            eligibility_confirmed=prospective["eligibility_confirmed"],
            resume_reviewed=prospective["resume_reviewed"],
            application_details_reviewed=prospective["application_details_reviewed"],
        )
        if not readiness["ready"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Complete the application readiness checklist before marking this application ready to apply.",
                    "blockers": readiness["blockers"],
                },
            )

    if (
        new_status in APPLIED_OR_LATER_STATUSES
        and current["applied_at"] is None
    ):
        assignments.append("applied_at = ?")
        values.append(_utc_now())

    assignments.append("updated_at = ?")
    values.append(_utc_now())
    values.append(application_id)

    connection.execute(
        f"""
        UPDATE applications
        SET {", ".join(assignments)}
        WHERE id = ?
        """,
        values,
    )

    connection.commit()

    result = _load_application(connection, application_id)

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="The updated application could not be loaded.",
        )

    return result


@router.delete("/{application_id}")
def delete_application(
    application_id: int = ApiPath(ge=1),
    connection: sqlite3.Connection = Depends(get_application_db),
) -> dict[str, Any]:
    """Remove only the user's pipeline entry; do not delete the job listing."""
    current = connection.execute(
        "SELECT id, job_id FROM applications WHERE id = ?",
        (application_id,),
    ).fetchone()

    if current is None:
        raise HTTPException(
            status_code=404,
            detail="Application was not found or has already been removed.",
        )

    connection.execute(
        "DELETE FROM applications WHERE id = ?",
        (application_id,),
    )
    connection.commit()

    return {
        "deleted": True,
        "application_id": int(current["id"]),
        "job_id": int(current["job_id"]),
    }
