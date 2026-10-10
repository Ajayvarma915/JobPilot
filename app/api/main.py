from __future__ import annotations

import os
import re
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Company, Job
from app.resume.evidence_selector import ResumeEvidenceSelector
from app.resume.evidence_store import (
    DEFAULT_STORE_PATH,
    MasterResumeEvidenceStore,
)
from app.resume.resume_builder import (
    ResumeBuildError,
    build_tailored_resume,
)


# ---------------------------------------------------------------------
# Paths and database
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

configured_database = os.getenv("JOBPILOT_DATABASE_PATH")

DATABASE_PATH = (
    Path(configured_database).expanduser().resolve()
    if configured_database
    else PROJECT_ROOT / "jobpilot.db"
)

EVIDENCE_STORE_PATH = DEFAULT_STORE_PATH

GENERATED_RESUMES_DIR = PROJECT_ROOT / "data" / "generated_resumes"

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request without creating a new DB."""
    if not DATABASE_PATH.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"JobPilot database was not found at {DATABASE_PATH}. "
                "Check JOBPILOT_DATABASE_PATH or restore jobpilot.db."
            ),
        )

    db = SessionLocal()

    try:
        yield db
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------
# API setup
# ---------------------------------------------------------------------

app = FastAPI(
    title="JobPilot API",
    description=(
        "Local API for job discovery, job matching workflows, "
        "resume evidence, and tailored resume generation."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------

class EvidenceSelectionRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=255)
    job_description: str = Field(min_length=20, max_length=80000)

    required_skills: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    preferred_skills: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    max_projects: int = Field(default=3, ge=0, le=10)


# ---------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------

def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def _serialize_job(job: Job, company: Company) -> dict[str, Any]:
    return {
        "id": job.id,
        "external_id": job.external_id,
        "title": job.title,
        "company": {
            "id": company.id,
            "name": company.name,
        },
        "location": job.location,
        "url": job.url,
        "description": job.description,
        "source": job.source,
        "experience_level": job.experience_level,
        "employment_type": job.employment_type,
        "posted_at": _serialize_datetime(job.posted_at),
        "first_seen_at": _serialize_datetime(job.first_seen_at),
        "last_seen_at": _serialize_datetime(job.last_seen_at),
        "is_active": job.is_active,
    }


def _relative_display_path(path: Path) -> str:
    """Return a project-relative path where possible."""
    resolved = path.resolve()

    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return resolved.name


def _load_evidence_store() -> dict[str, Any]:
    try:
        return MasterResumeEvidenceStore(EVIDENCE_STORE_PATH).load()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Master resume evidence store has not been created. "
                "Run: python -m scripts.build_master_resume_store"
            ),
        ) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read the master resume evidence store: {exc}",
        ) from exc


def _select_evidence(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    try:
        selector = ResumeEvidenceSelector(EVIDENCE_STORE_PATH)

        return selector.select_for_job(
            job_title=request.job_title,
            job_description=request.job_description,
            required_skills=request.required_skills,
            preferred_skills=request.preferred_skills,
            max_projects=request.max_projects,
        )

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Master resume evidence store is missing. "
                "Build it before selecting evidence."
            ),
        ) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not select resume evidence: {exc}",
        ) from exc


# ---------------------------------------------------------------------
# Root and health
# ---------------------------------------------------------------------

@app.get("/")
def root() -> dict[str, str]:
    return {
        "application": "JobPilot",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Check that the API can connect to the existing database."""
    try:
        db.execute(select(1))

        jobs_count = int(
            db.scalar(select(func.count()).select_from(Job)) or 0
        )

        companies_count = int(
            db.scalar(select(func.count()).select_from(Company)) or 0
        )

    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="The API cannot query the JobPilot database.",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
        "jobs_available": jobs_count,
        "companies_available": companies_count,
    }


# ---------------------------------------------------------------------
# Dashboard statistics
# ---------------------------------------------------------------------

@app.get("/api/dashboard/stats")
def dashboard_stats(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    total_jobs = int(
        db.scalar(select(func.count()).select_from(Job)) or 0
    )

    active_jobs = int(
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.is_active.is_(True))
        )
        or 0
    )

    inactive_jobs = total_jobs - active_jobs

    total_companies = int(
        db.scalar(select(func.count()).select_from(Company)) or 0
    )

    source_rows = db.execute(
        select(Job.source, func.count(Job.id))
        .group_by(Job.source)
        .order_by(func.count(Job.id).desc())
    ).all()

    experience_rows = db.execute(
        select(Job.experience_level, func.count(Job.id))
        .group_by(Job.experience_level)
        .order_by(func.count(Job.id).desc())
    ).all()

    return {
        "total_jobs": total_jobs,
        "active_jobs": active_jobs,
        "inactive_jobs": inactive_jobs,
        "total_companies": total_companies,
        "jobs_by_source": [
            {
                "source": source or "unknown",
                "count": int(count),
            }
            for source, count in source_rows
        ],
        "jobs_by_experience_level": [
            {
                "experience_level": level or "unknown",
                "count": int(count),
            }
            for level, count in experience_rows
        ],
    }


# ---------------------------------------------------------------------
# Job listing, searching, filtering, and pagination
# ---------------------------------------------------------------------

@app.get("/api/jobs")
def list_jobs(
    q: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    source: str | None = Query(default=None, max_length=100),
    active_only: bool = True,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    filters = []

    if active_only:
        filters.append(Job.is_active.is_(True))

    if q and q.strip():
        search_pattern = f"%{q.strip()}%"

        filters.append(
            or_(
                Job.title.ilike(search_pattern),
                Job.description.ilike(search_pattern),
                Company.name.ilike(search_pattern),
            )
        )

    if company and company.strip():
        filters.append(
            Company.name.ilike(f"%{company.strip()}%")
        )

    if location and location.strip():
        filters.append(
            Job.location.ilike(f"%{location.strip()}%")
        )

    if source and source.strip():
        filters.append(
            Job.source == source.strip()
        )

    join_condition = Job.company_id == Company.id

    count_statement = (
        select(func.count(Job.id))
        .select_from(Job)
        .join(Company, join_condition)
    )

    total = int(
        db.scalar(count_statement.where(*filters)) or 0
    )

    statement = (
        select(Job, Company)
        .join(Company, join_condition)
        .where(*filters)
        .order_by(Job.last_seen_at.desc(), Job.id.desc())
        .offset(offset)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    items = [
        _serialize_job(job, company_obj)
        for job, company_obj in rows
    ]

    return {
        "items": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + len(items) < total,
        },
        "filters": {
            "q": q,
            "company": company,
            "location": location,
            "source": source,
            "active_only": active_only,
        },
    }


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.scalar(
        select(Job).where(Job.id == job_id)
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job with ID {job_id} was not found.",
        )

    company = db.get(Company, job.company_id)

    if company is None:
        raise HTTPException(
            status_code=500,
            detail="The job refers to a missing company record.",
        )

    return _serialize_job(job, company)


# ---------------------------------------------------------------------
# Master resume evidence status
# ---------------------------------------------------------------------

@app.get("/api/evidence/summary")
def evidence_summary() -> dict[str, Any]:
    if not EVIDENCE_STORE_PATH.exists():
        return {
            "status": "not_ready",
            "record_count": 0,
            "verified_count": 0,
            "pending_count": 0,
            "counts_by_category": {},
        }

    data = _load_evidence_store()
    evidence = data.get("evidence", [])

    verified_count = sum(
        1
        for item in evidence
        if item.get("review", {}).get("user_verified") is True
    )

    counts_by_category: dict[str, int] = {}

    for item in evidence:
        category = str(item.get("category", "unknown"))
        counts_by_category[category] = (
            counts_by_category.get(category, 0) + 1
        )

    return {
        "status": "ready",
        "record_count": len(evidence),
        "verified_count": verified_count,
        "pending_count": len(evidence) - verified_count,
        "counts_by_category": dict(sorted(counts_by_category.items())),
        "source_resume": {
            "file": data.get("source_resume", {}).get("file"),
            "sha256": data.get("source_resume", {}).get("sha256"),
        },
    }


# ---------------------------------------------------------------------
# Resume evidence selection
# ---------------------------------------------------------------------

@app.post("/api/evidence/select")
def select_evidence(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    """Select current resume evidence for the submitted job description."""
    return _select_evidence(request)


# ---------------------------------------------------------------------
# Tailored resume generation
# ---------------------------------------------------------------------

@app.post("/api/resumes/generate", status_code=201)
def generate_resume(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    selection = _select_evidence(request)

    if not selection.get("selected_evidence"):
        raise HTTPException(
            status_code=409,
            detail=(
                "No verified evidence was selected for this job. "
                "Review the evidence queue or select a different job "
                "before generating a resume."
            ),
        )

    store_data = _load_evidence_store()

    slug = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        request.job_title,
    ).strip("_")[:60] or "Job"

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    filename = f"Tailored_{slug}_{timestamp}.docx"

    GENERATED_RESUMES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = GENERATED_RESUMES_DIR / filename
    audit_path = output_path.with_suffix(".audit.json")

    try:
        build_tailored_resume(
            selection,
            store_data,
            output_path,
            audit_path=audit_path,
        )
    except (OSError, ValueError, ResumeBuildError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not generate the tailored resume: {exc}",
        ) from exc

    return {
        "status": "created",
        "job_title": request.job_title,
        "resume_filename": filename,
        "resume_path": _relative_display_path(output_path),
        "audit_path": _relative_display_path(audit_path),
        "selected_evidence_count": len(
            selection["selected_evidence"]
        ),
        "download_url": f"/api/resumes/{filename}/download",
        "safety": {
            "verified_evidence_required": True,
            "claims_invented": False,
        },
    }


@app.get("/api/resumes/{filename}/download")
def download_resume(filename: str) -> FileResponse:
    """Download a generated DOCX, restricting access to the output folder."""
    if (
        filename in {".", ".."}
        or Path(filename).name != filename
        or not filename.lower().endswith(".docx")
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid resume filename.",
        )

    output_directory = GENERATED_RESUMES_DIR.resolve()
    output_path = (output_directory / filename).resolve()

    if output_path.parent != output_directory:
        raise HTTPException(
            status_code=400,
            detail="Invalid resume path.",
        )

    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Generated resume was not found.",
        )

    return FileResponse(
        path=output_path,
        filename=filename,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )