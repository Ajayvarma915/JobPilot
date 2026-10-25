from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from datetime import date, datetime, timezone
from pathlib import Path, PurePath
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

    @field_validator("resume_filename", "cover_letter_filename")
    @classmethod
    def validate_generated_filename(
        cls,
        value: str | None,
    ) -> str | None:
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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id)
                REFERENCES jobs(id)
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
            a.created_at,
            a.updated_at,
            j.title AS job_title,
            j.location AS job_location,
            j.url AS job_url,
            j.source AS job_source,
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
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "job": {
            "id": row["job_id"],
            "title": row["job_title"],
            "company": row["company_name"],
            "location": row["job_location"],
            "url": row["job_url"],
            "source": row["job_source"],
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
        SELECT id, status, applied_at
        FROM applications
        WHERE id = ?
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
    )

    for field in allowed_fields:
        if field not in changes:
            continue

        value = changes[field]

        if field == "follow_up_date":
            value = value.isoformat() if value else None

        assignments.append(f"{field} = ?")
        values.append(value)

    new_status = changes.get("status")

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