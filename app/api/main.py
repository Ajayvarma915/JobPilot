from __future__ import annotations

import ast
import logging
import math
import os
import re
from collections.abc import Generator
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.applications.tracker import router as applications_router
from pydantic import BaseModel, Field
from sqlalchemy import case, create_engine, func, or_, select
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
from app.services.job_match_cache import (
    ensure_match_cache_table,
    load_cached_matches,
    profile_fingerprint,
    release_cache_warmup,
    reserve_cache_warmup,
    save_cached_match,
)
from app.services.job_matcher import JobMatcher


logger = logging.getLogger(__name__)

from app.resume.resume_pdf_builder import build_tailored_resume_pdf
from app.resume.resume_evaluator import evaluate_generated_resume


PROJECT_ROOT = Path(__file__).resolve().parents[2]
configured_database = os.getenv("JOBPILOT_DATABASE_PATH")

DATABASE_PATH = (
    Path(configured_database).expanduser().resolve()
    if configured_database
    else PROJECT_ROOT / "jobpilot.db"
)

EVIDENCE_STORE_PATH = DEFAULT_STORE_PATH
GENERATED_RESUMES_DIR = PROJECT_ROOT / "data" / "generated_resumes"

engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

CANDIDATE_START_DATE = date(2025, 9, 18)

CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "hyderabad": "hyderabad",
}
CITY_DISPLAY_NAMES = {
    "bengaluru": "Bengaluru",
    "hyderabad": "Hyderabad",
}

SENIOR_ROLE_PATTERN = re.compile(
    r"\b(senior|staff|principal|distinguished|fellow|manager|director|"
    r"head|lead|chief|architect|vice president)\b",
    re.IGNORECASE,
)
INTERN_ROLE_PATTERN = re.compile(r"\b(intern|internship)\b", re.IGNORECASE)
PHD_PATTERN = re.compile(r"\bph\.?\s*d\.?\b|\bdoctorate\b", re.IGNORECASE)
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

RECOMMENDATION_LABELS = {
    "strong_match": "Strong match",
    "good_match": "Good match",
    "review": "Review",
    "low_match": "Low match",
}


def _candidate_experience_years() -> float:
    elapsed_days = max(0, (date.today() - CANDIDATE_START_DATE).days)
    return round(elapsed_days / 365.25, 3)


def _maximum_early_career_years() -> int:
    return max(1, math.floor(_candidate_experience_years()) + 1)


def _candidate_profile() -> Any:
    return replace(
        CANDIDATE_PROFILE,
        years_of_experience=_candidate_experience_years(),
    )


def get_db() -> Generator[Session, None, None]:
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
    version="0.5.3",
)

app.include_router(applications_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


class EvidenceSelectionRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=255)
    job_description: str = Field(min_length=20, max_length=80000)
    required_skills: list[str] = Field(default_factory=list, max_length=100)
    preferred_skills: list[str] = Field(default_factory=list, max_length=100)
    max_projects: int = Field(default=3, ge=0, le=10)


# ---------------------------------------------------------------------
# Location and role filtering
# ---------------------------------------------------------------------

def _normalize_city(value: str | None) -> str:
    if not value:
        return ""

    city = value.split(",", maxsplit=1)[0]
    city = re.sub(r"\s+", " ", city).strip().casefold()
    city = city.strip(" []'\"")
    return CITY_ALIASES.get(city, city)


def _location_entries(stored_location: str | None) -> list[str]:
    if not stored_location or not stored_location.strip():
        return []

    raw = stored_location.strip()

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


def _location_display_name(entry: str) -> str:
    city_key = _normalize_city(entry)
    if city_key in CITY_DISPLAY_NAMES:
        return CITY_DISPLAY_NAMES[city_key]
    return entry.split(",", maxsplit=1)[0].strip() or entry.strip()


def _location_contains_country(
    stored_location: str | None,
    country: str,
) -> bool:
    """Return true only when a listing explicitly names this country.

    This deliberately does not treat an unqualified "Remote" role as
    India-eligible; the listing must state India somewhere in its location.
    """
    if not stored_location or not country.strip():
        return False

    country_pattern = re.compile(
        rf"\b{re.escape(country.strip())}\b",
        re.IGNORECASE,
    )
    return any(
        bool(country_pattern.search(entry))
        for entry in _location_entries(stored_location)
    )


def _find_matching_location(
    stored_location: str | None,
    requested_location: str,
) -> str | None:
    requested_city = _normalize_city(requested_location)
    if not requested_city:
        return None

    # Country-level default used by the UI. Match India only when the source
    # explicitly names India, including locations such as "Remote - India".
    # An unspecified "Remote" listing is not assumed to be eligible.
    if requested_city == "india":
        for entry in _location_entries(stored_location):
            if re.search(r"\bindia\b", entry, re.IGNORECASE):
                return entry
        return None

    for entry in _location_entries(stored_location):
        if _normalize_city(entry) == requested_city:
            return entry

    return None


def _matches_requested_city(
    stored_location: str | None,
    requested_location: str,
) -> bool:
    """Compatibility helper for tests and callers that need a boolean."""
    return _find_matching_location(stored_location, requested_location) is not None


def _minimum_qualification_text(description: str) -> str:
    start = QUALIFICATION_START_PATTERN.search(description)
    remaining = description[start.end():] if start else description
    end = QUALIFICATION_END_PATTERN.search(remaining)
    return remaining[:end.start()] if end else remaining


def _extract_required_experience_years(
    description: str,
) -> float | None:
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
    """Shared eligibility rule for normal search and autocomplete."""
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
# Match serialization and background cache warm-up
# ---------------------------------------------------------------------

def _serialize_match(result: Any) -> dict[str, Any]:
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


def _warm_match_cache(
    job_ids: list[int],
    profile_hash: str,
) -> None:
    """Populate missing cache records using the application's database."""
    if not job_ids:
        return

    db: Session | None = None

    try:
        ensure_match_cache_table(engine)
        db = SessionLocal()

        profile = _candidate_profile()
        if profile_fingerprint(profile) != profile_hash:
            return

        matcher = JobMatcher(candidate_profile=profile)
        processed = 0

        for job_id in job_ids:
            job = db.get(Job, job_id)
            if job is None:
                continue

            if job.id in load_cached_matches(db, [job], profile_hash):
                continue

            match_data = _serialize_match(matcher.match(job))
            save_cached_match(db, job, profile_hash, match_data)
            processed += 1

            if processed % 20 == 0:
                db.commit()

        db.commit()

    except Exception:
        if db is not None:
            db.rollback()
        logger.exception("Job match-cache warm-up failed.")

    finally:
        if db is not None:
            db.close()
        release_cache_warmup(job_ids, profile_hash)


# ---------------------------------------------------------------------
# Resume evidence helpers
# ---------------------------------------------------------------------

def _relative_display_path(path: Path) -> str:
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
# Root, health and dashboard
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
def dashboard_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
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
# Searchable company directory
# ---------------------------------------------------------------------

@app.get("/api/companies")
def list_companies(
    q: str | None = Query(default=None, max_length=200),
    active_only: bool = True,
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    active_count = func.sum(
        case((Job.is_active.is_(True), 1), else_=0)
    )

    statement = (
        select(
            Company.id,
            Company.name,
            Company.website,
            Company.careers_url,
            func.count(Job.id).label("job_count"),
            active_count.label("active_job_count"),
            func.group_concat(func.distinct(Job.source)).label("sources"),
        )
        .outerjoin(Job, Job.company_id == Company.id)
        .group_by(
            Company.id,
            Company.name,
            Company.website,
            Company.careers_url,
        )
        .order_by(Company.name.asc())
    )

    if q and q.strip():
        statement = statement.where(
            Company.name.ilike(f"%{q.strip()}%")
        )

    items: list[dict[str, Any]] = []

    for row in db.execute(statement).all():
        job_count = int(row.job_count or 0)
        active_job_count = int(row.active_job_count or 0)

        if job_count == 0 or (active_only and active_job_count == 0):
            continue

        items.append(
            {
                "id": row.id,
                "name": row.name,
                "website": row.website,
                "careers_url": row.careers_url,
                "job_count": job_count,
                "active_job_count": active_job_count,
                "source_types": sorted(
                    part.strip()
                    for part in (row.sources or "").split(",")
                    if part.strip()
                ),
            }
        )

    return {
        "items": items[:limit],
        "total": len(items),
        "limit": limit,
        "active_only": active_only,
    }


# ---------------------------------------------------------------------
# Searchable location directory
# ---------------------------------------------------------------------

@app.get("/api/locations")
def list_locations(
    q: str | None = Query(default=None, max_length=200),
    active_only: bool = True,
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    statement = select(Job.id, Job.location)
    if active_only:
        statement = statement.where(Job.is_active.is_(True))

    rows = db.execute(statement).all()
    job_ids_by_city: dict[str, set[int]] = {}
    display_by_city: dict[str, str] = {}
    india_job_ids: set[int] = set()

    for job_id, stored_location in rows:
        if _location_contains_country(stored_location, "India"):
            india_job_ids.add(int(job_id))

        for entry in _location_entries(stored_location):
            city_key = _normalize_city(entry)
            if not city_key:
                continue

            display = CITY_DISPLAY_NAMES.get(
                city_key,
                _location_display_name(entry),
            )
            display_by_city.setdefault(city_key, display)
            job_ids_by_city.setdefault(city_key, set()).add(int(job_id))

    items: list[dict[str, Any]] = []
    for city_key, job_ids in job_ids_by_city.items():
        name = display_by_city[city_key]

        if q and q.strip():
            needle = q.strip().casefold()
            if needle not in name.casefold() and needle not in city_key:
                continue

        items.append(
            {
                "city": name,
                "value": name,
                "job_count": len(job_ids),
            }
        )

    # Offer a country-level India option so the UI can default to India while
    # retaining the explicit "All locations" option for global searches.
    # Respect text search for directory queries such as ?q=hyderabad.
    if india_job_ids and (
        not q
        or not q.strip()
        or q.strip().casefold() in "india"
    ):
        items.append(
            {
                "city": "India",
                "value": "India",
                "job_count": len(india_job_ids),
            }
        )

    items.sort(
        key=lambda item: (
            0 if item["city"].casefold() == "india" else 1,
            -item["job_count"],
            item["city"].casefold(),
        )
    )

    return {
        "items": items[:limit],
        "total": len(items),
        "active_only": active_only,
    }


# ---------------------------------------------------------------------
# Company-aware, filter-aware job autocomplete
# ---------------------------------------------------------------------

@app.get("/api/job-suggestions")
def job_suggestions(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
    career_level: Literal["early", "all"] = Query(default="early"),
    company: str | None = Query(default=None, max_length=200),
    location: str | None = Query(default=None, max_length=200),
    source: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """
    Suggest job titles by searching both job titles and company names.

    The selected company, location, source and career-level filters are
    applied before a title is presented, so autocomplete does not
    recommend a role that the corresponding filtered search will exclude.
    """
    query = q.strip()

    if len(query) < 2:
        return {"query": query, "items": []}

    pattern = f"%{query}%"
    filters = [
        Job.is_active.is_(True),
        or_(
            Job.title.ilike(pattern),
            Company.name.ilike(pattern),
        ),
    ]

    if company and company.strip():
        filters.append(Company.name.ilike(f"%{company.strip()}%"))

    if source and source.strip():
        filters.append(Job.source == source.strip())

    statement = (
        select(Job, Company)
        .join(Company, Job.company_id == Company.id)
        .where(*filters)
        .order_by(Job.title.asc(), Company.name.asc())
        .limit(5000)
    )

    grouped: dict[str, dict[str, Any]] = {}
    query_lower = query.casefold()

    for job, company_obj in db.execute(statement).all():
        if location and location.strip():
            if _find_matching_location(job.location, location) is None:
                continue

        if career_level == "early" and not _is_early_career_suitable(
            job.title,
            job.description or "",
        ):
            continue

        clean_title = (job.title or "").strip()
        clean_company = (company_obj.name or "").strip()

        if not clean_title:
            continue

        key = clean_title.casefold()

        if key not in grouped:
            grouped[key] = {
                "title": clean_title,
                "count": 0,
                "companies": set(),
                "matched_by": set(),
            }

        item = grouped[key]
        item["count"] += 1

        if clean_company:
            item["companies"].add(clean_company)

        # Track whether the query matched the title or company name.
        # The frontend uses this to preserve company-search intent.
        if query_lower in clean_title.casefold():
            item["matched_by"].add("title")

        if query_lower in clean_company.casefold():
            item["matched_by"].add("company")

    results = list(grouped.values())

    results.sort(
        key=lambda item: (
            not item["title"].casefold().startswith(query_lower),
            query_lower not in item["title"].casefold(),
            -item["count"],
            item["title"].casefold(),
        )
    )

    return {
        "query": query,
        "items": [
            {
                "title": item["title"],
                "count": item["count"],
                "companies": sorted(item["companies"]),
                "matched_by": sorted(item["matched_by"]),
            }
            for item in results[:limit]
        ],
    }


# ---------------------------------------------------------------------
# Job search and persistent match cache
# ---------------------------------------------------------------------

@app.get("/api/jobs")
def list_jobs(
    background_tasks: BackgroundTasks,
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
    # Use the engine attached to this request's session; tests may override it.
    request_engine = db.get_bind()
    ensure_match_cache_table(request_engine)

    filters = []

    if active_only:
        filters.append(Job.is_active.is_(True))

    if q and q.strip():
        pattern = f"%{q.strip()}%"
        filters.append(
            or_(
                Job.title.ilike(pattern),
                Job.description.ilike(pattern),
                Company.name.ilike(pattern),
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

    candidates: list[tuple[Job, Company, str | None, int]] = []

    for job, company_obj in db.execute(statement).all():
        matched_location = None

        if location and location.strip():
            matched_location = _find_matching_location(
                job.location,
                location,
            )
            if matched_location is None:
                continue

        if career_level == "early" and not _is_early_career_suitable(
            job.title,
            job.description or "",
        ):
            continue

        direct_title_match = int(
            bool(
                q
                and q.strip()
                and q.strip().casefold() in job.title.casefold()
            )
        )

        candidates.append(
            (job, company_obj, matched_location, direct_title_match)
        )

    total = len(candidates)
    profile = _candidate_profile()
    profile_hash = profile_fingerprint(profile)

    cached_matches = load_cached_matches(
        db,
        (row[0] for row in candidates),
        profile_hash,
    )
    cache_ready = len(cached_matches) == len(candidates)

    page_results: list[
        tuple[Job, Company, str | None, int, dict[str, Any]]
    ] = []

    if cache_ready:
        ranked = [
            (
                job,
                company_obj,
                matched_location,
                title_match,
                cached_matches[int(job.id)],
            )
            for job, company_obj, matched_location, title_match in candidates
        ]

        ranked.sort(
            key=lambda row: (
                float(row[4].get("score", 0)),
                row[3],
                (
                    row[0].last_seen_at.isoformat()
                    if row[0].last_seen_at
                    else ""
                ),
                row[0].id or 0,
            ),
            reverse=True,
        )
        page_results = ranked[offset:offset + limit]

    else:
        page_candidates = candidates[offset:offset + limit]

        if any(
            int(row[0].id) not in cached_matches
            for row in page_candidates
        ):
            matcher = JobMatcher(candidate_profile=profile)
        else:
            matcher = None

        for job, company_obj, matched_location, title_match in page_candidates:
            job_id = int(job.id)
            match_data = cached_matches.get(job_id)

            if match_data is None:
                assert matcher is not None
                match_data = _serialize_match(matcher.match(job))
                save_cached_match(db, job, profile_hash, match_data)
                cached_matches[job_id] = match_data

            page_results.append(
                (
                    job,
                    company_obj,
                    matched_location,
                    title_match,
                    match_data,
                )
            )

        db.commit()

        page_results.sort(
            key=lambda row: (
                float(row[4].get("score", 0)),
                row[3],
                (
                    row[0].last_seen_at.isoformat()
                    if row[0].last_seen_at
                    else ""
                ),
                row[0].id or 0,
            ),
            reverse=True,
        )

    pending_ids = [
        int(job.id)
        for job, _, _, _ in candidates
        if int(job.id) not in cached_matches
    ]

    scheduled_ids: list[int] = []

    # Do not warm IDs from test databases in the real application database.
    if request_engine is engine and pending_ids:
        scheduled_ids = reserve_cache_warmup(
            pending_ids,
            profile_hash,
        )

        if scheduled_ids:
            background_tasks.add_task(
                _warm_match_cache,
                scheduled_ids,
                profile_hash,
            )

    items: list[dict[str, Any]] = []

    for job, company_obj, matched_location, _, match_data in page_results:
        items.append(
            {
                "id": job.id,
                "external_id": job.external_id,
                "title": job.title,
                "company": {
                    "id": company_obj.id,
                    "name": company_obj.name,
                },
                "location": matched_location or job.location,
                "all_locations": job.location,
                "url": job.url,
                "description": job.description,
                "source": job.source,
                "experience_level": job.experience_level,
                "employment_type": job.employment_type,
                "posted_at": (
                    job.posted_at.isoformat() if job.posted_at else None
                ),
                "first_seen_at": (
                    job.first_seen_at.isoformat()
                    if job.first_seen_at
                    else None
                ),
                "last_seen_at": (
                    job.last_seen_at.isoformat()
                    if job.last_seen_at
                    else None
                ),
                "is_active": job.is_active,
                "match": match_data,
            }
        )

    cache_ready = len(cached_matches) == len(candidates)

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
                (
                    "explicit_country_match"
                    if _normalize_city(location) == "india"
                    else "match_any_listed_city"
                )
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
            "sort": (
                "candidate_match_score_descending"
                if cache_ready
                else "recent_listings_while_cache_warms"
            ),
        },
        "match_cache": {
            "ready": cache_ready,
            "pending_jobs": len(pending_ids),
            "scheduled_jobs": len(scheduled_ids),
        },
    }


@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    ensure_match_cache_table(db.get_bind())

    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job with ID {job_id} was not found.",
        )

    company_obj = db.get(Company, job.company_id)
    if company_obj is None:
        raise HTTPException(
            status_code=500,
            detail="The job refers to a missing company record.",
        )

    profile = _candidate_profile()
    profile_hash = profile_fingerprint(profile)
    cached = load_cached_matches(db, [job], profile_hash)

    if job_id in cached:
        match_data = cached[job_id]
    else:
        matcher = JobMatcher(candidate_profile=profile)
        match_data = _serialize_match(matcher.match(job))
        save_cached_match(db, job, profile_hash, match_data)
        db.commit()

    return {
        "id": job.id,
        "external_id": job.external_id,
        "title": job.title,
        "company": {"id": company_obj.id, "name": company_obj.name},
        "location": job.location,
        "all_locations": job.location,
        "url": job.url,
        "description": job.description,
        "source": job.source,
        "experience_level": job.experience_level,
        "employment_type": job.employment_type,
        "posted_at": job.posted_at.isoformat() if job.posted_at else None,
        "first_seen_at": (
            job.first_seen_at.isoformat() if job.first_seen_at else None
        ),
        "last_seen_at": (
            job.last_seen_at.isoformat() if job.last_seen_at else None
        ),
        "is_active": job.is_active,
        "match": match_data,
    }


# ---------------------------------------------------------------------
# Resume evidence endpoints
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


@app.post("/api/evidence/select")
def select_evidence(
    request: EvidenceSelectionRequest,
) -> dict[str, Any]:
    return _select_evidence(request)


# ---------------------------------------------------------------------
# Resume generation and download
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
    pdf_filename = f"Tailored_{slug}_{timestamp}.pdf"

    GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GENERATED_RESUMES_DIR / filename
    pdf_output_path = GENERATED_RESUMES_DIR / pdf_filename
    audit_path = output_path.with_suffix(".audit.json")

    try:
        build_tailored_resume(
            selection,
            store_data,
            output_path,
            audit_path=audit_path,
        )
        build_tailored_resume_pdf(
            selection,
            store_data,
            pdf_output_path,
        )
        evaluation = evaluate_generated_resume(
            docx_path=output_path,
            pdf_path=pdf_output_path,
            selection=selection,
            store=store_data,
        )
    except Exception as exc:
        # Do not leave partial or unchecked outputs presented as successful files.
        for generated_path in (output_path, pdf_output_path, audit_path):
            try:
                generated_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(
            status_code=422,
            detail=f"Could not generate and validate the tailored resume: {exc}",
        ) from exc

    return {
        "status": "created",
        "job_title": request.job_title,
        "resume_filename": filename,
        "resume_path": _relative_display_path(output_path),
        "audit_path": _relative_display_path(audit_path),
        "selected_evidence_count": len(selection["selected_evidence"]),
        "download_url": f"/api/resumes/{filename}/download",
        "pdf_filename": pdf_filename,
        "pdf_download_url": f"/api/resumes/{pdf_filename}/download",
        "evaluation": evaluation,
        "safety": {
            "verified_evidence_required": True,
            "claims_invented": False,
        },
    }


@app.get("/api/resumes/{filename}/download")
def download_resume(filename: str) -> FileResponse:
    suffix = Path(filename).suffix.lower()
    if (
        filename in {".", ".."}
        or Path(filename).name != filename
        or suffix not in {".docx", ".pdf"}
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid resume filename. Only generated DOCX and PDF files can be downloaded.",
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

    media_type = (
        "application/pdf"
        if suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path=output_path, filename=filename, media_type=media_type)
