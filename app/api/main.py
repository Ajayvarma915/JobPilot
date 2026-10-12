from __future__ import annotations

import ast
import math
import os
import re
from collections.abc import Generator
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Company, Job
from app.profile.candidate_profile import CANDIDATE_PROFILE
from app.resume.evidence_selector import ResumeEvidenceSelector
from app.resume.evidence_store import (
    DEFAULT_STORE_PATH,
    MasterResumeEvidenceStore,
)
from app.resume.resume_builder import (
    ResumeBuildError,
    build_tailored_resume,
)
from app.services.job_matcher import JobMatcher


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

# Candidate's TCS employment start date.
CANDIDATE_START_DATE = date(2025, 9, 18)


def _candidate_experience_years() -> float:
    elapsed_days = max(0, (date.today() - CANDIDATE_START_DATE).days)
    return round(elapsed_days / 365.25, 3)


def _maximum_early_career_years() -> int:
    # Permit a stretch of up to the next whole year of required experience.
    return max(1, math.floor(_candidate_experience_years()) + 1)


def _create_job_matcher() -> JobMatcher:
    # The profile snapshot previously contained 0.0 years. Use the current
    # TCS tenure for API-based scoring without changing the stored profile.
    profile = replace(
        CANDIDATE_PROFILE,
        years_of_experience=_candidate_experience_years(),
    )
    return JobMatcher(candidate_profile=profile)


def get_db() -> Generator[Session, None, None]:
    """Provide one database session per request."""
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


app = FastAPI(
    title="JobPilot API",
    description=(
        "Local API for job discovery, candidate-job matching, "
        "resume evidence, and tailored resume generation."
    ),
    version="0.3.0",
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


class EvidenceSelectionRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=255)
    job_description: str = Field(min_length=20, max_length=80000)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=100)
    max_projects: int = Field(default=3, ge=0, le=10)


# ---------------------------------------------------------------------
# City matching and early-career filtering
# ---------------------------------------------------------------------

CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "hyderabad": "hyderabad",
}

SENIOR_ROLE_PATTERN = re.compile(
    r"\b(senior|staff|principal|distinguished|fellow|manager|director|"
    r"head|lead|chief|architect|vice president)\b",
    re.IGNORECASE,
)

INTERN_ROLE_PATTERN = re.compile(
    r"\b(intern|internship)\b",
    re.IGNORECASE,
)

PHD_PATTERN = re.compile(
    r"\bph\.?\s*d\.?\b|\bdoctorate\b",
    re.IGNORECASE,
)

QUALIFICATION_START_PATTERN = re.compile(
    r"\b(?:minimum|basic|required)\s+qualifications?\b",
    re.IGNORECASE,
)

QUALIFICATION_END_PATTERN = re.compile(
    r"\b(?:preferred qualifications?|responsibilities|what you(?:'|’)ll do|"
    r"about the job|about the role|equal opportunity)\b",
    re.IGNORECASE,
)

YEARS_BEFORE_EXPERIENCE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*\+?\s+years?\b[^\n]{0,120}\bexperience\b",
    re.IGNORECASE,
)

EXPERIENCE_BEFORE_YEARS_PATTERN = re.compile(
    r"\bexperience\b[^\n]{0,100}\b(\d+(?:\.\d+)?)\s*\+?\s+years?\b",
    re.IGNORECASE,
)


def _normalize_city(value: str | None) -> str:
    if not value:
        return ""

    city = value.split(",", maxsplit=1)[0]
    city = re.sub(r"\s+", " ", city).strip().casefold()
    city = city.strip(" []'\"")

    return CITY_ALIASES.get(city, city)


def _location_entries(stored_location: str | None) -> list[str]:
    """Split a stored multi-city string into individual location entries."""
    if not stored_location or not stored_location.strip():
        return []

    raw = stored_location.strip()

    # Some older data may store a Python list representation as a string.
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, (list, tuple)):
                entries = [
                    str(item).strip()
                    for item in parsed
                    if str(item).strip()
                ]
                if entries:
                    return entries
        except (ValueError, SyntaxError):
            pass

    return [
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"[;|\r\n]+", raw)
        if part.strip()
    ]


def _find_matching_location(
    stored_location: str | None,
    requested_location: str,
) -> str | None:
    """Return the original location entry matching the requested city."""
    requested_city = _normalize_city(requested_location)
    if not requested_city:
        return None

    for entry in _location_entries(stored_location):
        if _normalize_city(entry) == requested_city:
            return entry

    return None


def _minimum_qualification_text(description: str) -> str:
    start = QUALIFICATION_START_PATTERN.search(description)
    remaining = description[start.end():] if start else description

    end = QUALIFICATION_END_PATTERN.search(remaining)
    return remaining[:end.start()] if end else remaining


def _extract_required_experience_years(
    description: str,
) -> float | None:
    """Read minimum qualifications, avoiding preferred-only experience."""
    minimum_text = _minimum_qualification_text(description)
    values: list[float] = []

    for pattern in (
        YEARS_BEFORE_EXPERIENCE_PATTERN,
        EXPERIENCE_BEFORE_YEARS_PATTERN,
    ):
        for match in pattern.finditer(minimum_text):
            try:
                values.append(float(match.group(1)))
            except ValueError:
                continue

    return max(values) if values else None


def _requires_phd(description: str) -> bool:
    return bool(PHD_PATTERN.search(_minimum_qualification_text(description)))


def _is_early_career_suitable(
    title: str,
    description: str,
) -> bool:
    """Exclude obvious senior, management, internship and doctoral roles."""
    clean_title = re.sub(r"\s+", " ", title).strip()
    if not clean_title:
        return False

    if SENIOR_ROLE_PATTERN.search(clean_title):
        return False

    if INTERN_ROLE_PATTERN.search(clean_title):
        return False

    if PHD_PATTERN.search(clean_title) or _requires_phd(description):
        return False

    required_years = _extract_required_experience_years(description)

    if (
        required_years is not None
        and required_years > _maximum_early_career_years()
    ):
        return False

    return True


# ---------------------------------------------------------------------
# Structured candidate-job match serialization
# ---------------------------------------------------------------------

RECOMMENDATION_LABELS = {
    "strong_match": "Strong match",
    "good_match": "Good match",
    "review": "Review",
    "low_match": "Low match",
}


def _serialize_match(job: Job) -> dict[str, Any]:
    """Use the existing structured JobMatcher; do not create a new formula."""
    result = _create_job_matcher().match(job)

    return {
        "score": result.score,
        "recommendation": result.recommendation,
        "recommendation_label": RECOMMENDATION_LABELS.get(
            result.recommendation,
            "Review",
        ),
        "role_family": result.role_family,
        "seniority": result.seniority,
        "required_years": result.required_years,
        "analysis_confidence": result.analysis_confidence,
        "score_breakdown": {
            "role": result.role_score,
            "seniority": result.seniority_score,
            "experience": result.experience_score,
            "skills": result.skills_score,
            "education": result.education_score,
            "location": result.location_score,
        },
        "matched_required_skills": list(result.matched_skills),
        "missing_required_skills": list(result.missing_required_skills),
        "required_skills": list(result.required_skills),
        "matched_preferred_skills": list(result.matched_preferred_skills),
        "preferred_skills": list(result.preferred_skills),
        "required_education": list(result.required_education),
        "hard_constraints": list(result.hard_constraints),
        "reasons": list(result.reasons),
        "concerns": list(result.concerns),
    }


# ---------------------------------------------------------------------
# General serialization and evidence helpers
# ---------------------------------------------------------------------

def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _relative_display_path(path: Path) -> str:
    resolved = path.resolve()

    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return resolved.name


def _serialize_job_without_matching(
    job: Job,
    company: Company,
    matched_location: str | None = None,
) -> dict[str, Any]:
    return {
        "id": job.id,
        "external_id": job.external_id,
        "title": job.title,
        "company": {"id": company.id, "name": company.name},
        "location": matched_location or job.location,
        "all_locations": job.location,
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
# Root, health and dashboard stats
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
def health(
    db: Session = Depends(get_db),
) -> dict[str, Any]:
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
        ) or 0
    )
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
        "inactive_jobs": total_jobs - active_jobs,
        "total_companies": total_companies,
        "jobs_by_source": [
            {"source": source or "unknown", "count": int(count)}
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
# Job listing, searching, matching, filtering and pagination
# ---------------------------------------------------------------------

@app.get("/api/jobs")
def list_jobs(
    q: str | None = Query(default=None, max_length=200),
    company: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    source: str | None = Query(default=None, max_length=100),
    active_only: bool = True,
    career_level: Literal["early", "all"] = Query(default="early"),
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
        filters.append(Company.name.ilike(f"%{company.strip()}%"))

    if source and source.strip():
        filters.append(Job.source == source.strip())

    statement = (
        select(Job, Company)
        .join(Company, Job.company_id == Company.id)
        .where(*filters)
        .order_by(Job.last_seen_at.desc(), Job.id.desc())
    )

    candidate_rows = db.execute(statement).all()
    scored_rows: list[
        tuple[Job, Company, str | None, dict[str, Any], int]
    ] = []

    for job, company_obj in candidate_rows:
        matched_location: str | None = None

        if location and location.strip():
            matched_location = _find_matching_location(job.location, location)
            if matched_location is None:
                continue

        if career_level == "early" and not _is_early_career_suitable(
            job.title,
            job.description or "",
        ):
            continue

        match = _serialize_match(job)
        direct_title_match = int(
            bool(
                q
                and q.strip()
                and q.strip().casefold() in job.title.casefold()
            )
        )

        scored_rows.append(
            (
                job,
                company_obj,
                matched_location,
                match,
                direct_title_match,
            )
        )

    # Candidate fit is primary; a direct title match breaks ties.
    scored_rows.sort(
        key=lambda row: (
            row[3]["score"],
            row[4],
            row[0].last_seen_at.isoformat() if row[0].last_seen_at else "",
            row[0].id or 0,
        ),
        reverse=True,
    )

    total = len(scored_rows)
    page_rows = scored_rows[offset:offset + limit]

    items: list[dict[str, Any]] = []
    for job, company_obj, matched_location, match, _ in page_rows:
        serialized = _serialize_job_without_matching(
            job,
            company_obj,
            matched_location,
        )
        serialized["match"] = match
        items.append(serialized)

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
            "location_mode": (
                "match_any_listed_city"
                if location and location.strip()
                else None
            ),
            "source": source,
            "active_only": active_only,
            "career_level": career_level,
            "maximum_required_years": (
                _maximum_early_career_years()
                if career_level == "early"
                else None
            ),
            "candidate_experience_years": _candidate_experience_years(),
            "sort": "candidate_match_score_descending",
        },
    }


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    job = db.scalar(select(Job).where(Job.id == job_id))

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

    serialized = _serialize_job_without_matching(job, company)
    serialized["match"] = _serialize_match(job)
    return serialized


# ---------------------------------------------------------------------
# Resume evidence status and selection
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
        counts_by_category[category] = counts_by_category.get(category, 0) + 1

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


@app.post("/api/evidence/select")
def select_evidence(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    return _select_evidence(request)


# ---------------------------------------------------------------------
# Tailored resume generation and download
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
    slug = (
        re.sub(r"[^A-Za-z0-9]+", "_", request.job_title).strip("_")[:60]
        or "Job"
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"Tailored_{slug}_{timestamp}.docx"

    GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
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
        "selected_evidence_count": len(selection["selected_evidence"]),
        "download_url": f"/api/resumes/{filename}/download",
        "safety": {
            "verified_evidence_required": True,
            "claims_invented": False,
        },
    }


@app.get("/api/resumes/{filename}/download")
def download_resume(filename: str) -> FileResponse:
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