from __future__ import annotations

import ast
import json
import logging
import math
import os
import re
import sqlite3
from collections.abc import Generator
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.applications.tracker import router as applications_router
from app.email.gmail_integration import router as email_router
from pydantic import BaseModel, Field
from sqlalchemy import case, create_engine, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import resolve_database_path
from app.ai.fit_analysis import (
    FIT_SCHEMA,
    PROMPT_VERSION as FIT_PROMPT_VERSION,
    SYSTEM_PROMPT as FIT_SYSTEM_PROMPT,
    build_prompt as build_fit_prompt,
    make_validator as make_fit_validator,
    merge_fit,
)
from app.ai.providers import get_provider
from app.ai.runner import run_structured
from app.services.sync_summary import build_change_summary
from app.services.job_compare import build_comparison
from app.resume.tailoring_report import FabricationError, build_tailoring_report, fabrication_check
from app.applications.answers import (
    QUESTION_KEYS as ANSWER_QUESTION_KEYS,
    approval_blockers as answer_approval_blockers,
    classify_question,
    draft_answer,
    unresolved_placeholders as unresolved_answer_placeholders,
)
from app.applications.cover_letters import cover_letter_docx, cover_letter_pdf, generate_cover_letter
from app.applications.profile_facts import load_profile_facts
from app.services.opportunities import ACTIONS as OPPORTUNITY_ACTIONS, score_opportunity, skill_gap_report
from app.services.source_health import (
    build_health_report,
    load_health_rows,
    load_registry_companies,
)
from app.services.target_role_policy import (
    early_career_title_exclusion,
    extract_minimum_experience_years,
    matches_software_role_family,
    requires_phd,
)
from app.db.models import Company, CoverLetterVersion, EmployerAnswer, Job, ResumeVersion
from app.profile.candidate_profile import CANDIDATE_PROFILE
from app.ai.jd_insights import analyze_job_description_with_ollama
from app.config import OLLAMA_MODEL
from app.ai.ollama_client import (
    OllamaError,
    OllamaModelNotFoundError,
    OllamaUnavailableError,
    get_status as get_ollama_status,
)
from app.services.jd_analyzer import analyze_job_description as analyze_job_description_rules
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
DATABASE_PATH = resolve_database_path()

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

# Role-family, seniority, PhD and experience rules live in
# app/services/target_role_policy.py (single source of truth).

TARGET_COMPENSATION_FLOOR_LPA = 25.0
_LPA_UNIT = r"(?:lpa|lakhs?\s*(?:per\s+annum|p\.?a\.?|pa))"
_LPA_RANGE_PATTERN = re.compile(
    rf"(?:₹|inr\s*)?\s*(\d{{1,3}}(?:\.\d+)?)\s*(?:-|–|to)\s*"
    rf"(?:₹|inr\s*)?\s*(\d{{1,3}}(?:\.\d+)?)\s*{_LPA_UNIT}",
    re.IGNORECASE,
)
_LPA_SINGLE_PATTERN = re.compile(
    rf"(?:₹|inr\s*)?\s*(\d{{1,3}}(?:\.\d+)?)\s*{_LPA_UNIT}",
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


def _unique_strings(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        return ()
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)


def _candidate_profile() -> Any:
    """Use parsed facts from the reusable local profile when available.

    The code-based profile remains the fallback for older databases or when
    the user has not imported a master resume yet.
    """
    base_profile = replace(
        CANDIDATE_PROFILE,
        years_of_experience=_candidate_experience_years(),
    )

    if not DATABASE_PATH.is_file():
        return base_profile

    connection: sqlite3.Connection | None = None
    try:
        # sqlite3.Connection's context manager commits or rolls back; it does
        # not close the connection. Close explicitly so Windows can release
        # temporary SQLite files immediately after profile matching tests.
        connection = sqlite3.connect(str(DATABASE_PATH), timeout=1)
        row = connection.execute(
            "SELECT resume_facts_json FROM candidate_profile_vault WHERE id = 1"
        ).fetchone()
    except (sqlite3.Error, OSError):
        return base_profile
    finally:
        if connection is not None:
            connection.close()

    if not row or not row[0]:
        return base_profile

    try:
        facts = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return base_profile
    if not isinstance(facts, dict):
        return base_profile

    skills = _unique_strings(facts.get("skills")) or base_profile.technical_skills
    programming_languages = (
        _unique_strings(facts.get("programming_languages"))
        or base_profile.programming_languages
    )
    frameworks = _unique_strings(facts.get("frameworks")) or base_profile.frameworks
    tools = _unique_strings(facts.get("tools")) or base_profile.tools
    concepts = _unique_strings(facts.get("concepts")) or base_profile.concepts

    education_items: list[str] = []
    for item in facts.get("education", []) if isinstance(facts.get("education"), list) else []:
        if not isinstance(item, dict):
            continue
        text = " — ".join(
            value.strip()
            for value in (item.get("degree"), item.get("field_of_study"), item.get("institution"))
            if isinstance(value, str) and value.strip()
        )
        if not text and isinstance(item.get("raw_text"), str):
            text = item["raw_text"].strip()
        if text:
            education_items.append(text)

    certifications = _unique_strings([
        item.get("name", "")
        for item in facts.get("certifications", [])
        if isinstance(item, dict)
    ]) if isinstance(facts.get("certifications"), list) else ()

    project_skills: list[str] = []
    if isinstance(facts.get("projects"), list):
        for project in facts["projects"]:
            if isinstance(project, dict):
                project_skills.extend(
                    value for value in project.get("technologies", [])
                    if isinstance(value, str)
                )
    project_skills = list(_unique_strings(project_skills))

    experience = facts.get("experience", [])
    has_internship = any(
        isinstance(item, dict)
        and "intern" in str(item.get("role") or "").casefold()
        for item in experience
    ) if isinstance(experience, list) else False

    frontend_base = set(value.casefold() for value in base_profile.frontend_skills)
    frontend_skills = tuple(skill for skill in skills if skill.casefold() in frontend_base)
    if not frontend_skills:
        frontend_skills = base_profile.frontend_skills

    return replace(
        base_profile,
        education=_unique_strings(education_items) or base_profile.education,
        technical_skills=skills,
        programming_languages=programming_languages,
        frontend_skills=frontend_skills,
        frameworks=frameworks,
        tools=tools,
        concepts=concepts,
        project_skills=tuple(project_skills) or base_profile.project_skills,
        certifications=certifications or base_profile.certifications,
        internship_experience=has_internship or base_profile.internship_experience,
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
app.include_router(email_router)

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
    job_id: int | None = Field(default=None, description="Stored job this resume is generated for (links the version to it).")


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

    # The India default includes locations explicitly in India and clearly
    # country-unrestricted remote labels. Remote roles naming another country
    # (for example, "Remote - Brazil" or "Remote, US") remain excluded.
    # This lets users see generic Remote roles, while employer-specific country
    # restrictions still need to be checked before applying.
    if requested_city == "india":
        entries = _location_entries(stored_location)

        for entry in entries:
            if re.search(r"\bindia\b", entry, re.IGNORECASE):
                return entry

        unrestricted_remote_pattern = re.compile(
            r"^(?:(?:fully\s+)?remote(?:\s+(?:worldwide|globally|anywhere))?"
            r"|work\s+from\s+anywhere|anywhere\s+in\s+the\s+world)$",
            re.IGNORECASE,
        )
        if entries and all(
            unrestricted_remote_pattern.fullmatch(entry.strip())
            for entry in entries
        ):
            return entries[0]

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


def _extract_required_experience_years(
    description: str,
) -> float | None:
    """Minimum years stated in the JD (lower bound of ranges); None if unstated."""
    return extract_minimum_experience_years(description)


def _requires_phd(description: str) -> bool:
    return requires_phd(description)


def _is_target_software_role(title: str) -> bool:
    """Return true for software-engineering title families in the default feed."""
    return matches_software_role_family(title)


def _extract_salary_lpa(description: str) -> tuple[float, float] | None:
    """Extract an explicitly stated INR LPA range; never infer undisclosed pay."""
    text = description or ""
    range_match = _LPA_RANGE_PATTERN.search(text)
    if range_match:
        low, high = (float(range_match.group(1)), float(range_match.group(2)))
        return (min(low, high), max(low, high))
    single_match = _LPA_SINGLE_PATTERN.search(text)
    if single_match:
        value = float(single_match.group(1))
        return (value, value)
    return None


def _compensation_signal(description: str) -> dict[str, Any]:
    salary = _extract_salary_lpa(description)
    if salary is None:
        return {
            "min_lpa": None,
            "max_lpa": None,
            "status": "not_disclosed",
            "target_floor_lpa": TARGET_COMPENSATION_FLOOR_LPA,
        }
    low, high = salary
    if low >= 30.0:
        signal = "target_30_plus"
    elif low >= TARGET_COMPENSATION_FLOOR_LPA:
        signal = "target_25_plus"
    elif high >= TARGET_COMPENSATION_FLOOR_LPA:
        signal = "target_possible"
    else:
        signal = "below_target"
    return {
        "min_lpa": low,
        "max_lpa": high,
        "status": signal,
        "target_floor_lpa": TARGET_COMPENSATION_FLOOR_LPA,
    }


def _is_early_career_suitable(
    title: str,
    description: str,
) -> bool:
    """Shared eligibility rule for normal search and autocomplete."""
    if early_career_title_exclusion(title) is not None:
        return False
    if _requires_phd(description):
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
        # Transparency fields (older cached rows may not have them).
        "mismatches": {k: list(v) for k, v in (getattr(result, "mismatches", None) or {}).items()},
        "weights": dict(getattr(result, "weights_used", None) or {}),
        "eligibility": {
            "status": getattr(result, "eligibility_status", None),
            "reasons": list(getattr(result, "eligibility_reasons", None) or []),
            "capped": bool(getattr(result, "eligibility_capped", False)),
        },
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


@app.get("/api/sources/health")
def source_health(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Read-only coverage view: every registry company with its source state.

    States come from data/target_companies.json (what is configured and
    verified) combined with recorded fetch history. Nothing is written here.
    """
    try:
        companies = load_registry_companies()
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="The company source registry could not be read.",
        ) from exc
    try:
        rows = load_health_rows(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="The API cannot read source health history.",
        ) from exc
    return build_health_report(companies, rows)


@app.get("/api/sync/summary")
def sync_summary(
    days: int = Query(7, ge=1, le=90, description="Look-back window in days (7 = weekly, 1 = daily)."),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """What changed in the stored jobs recently: new, updated, reactivated and removed.

    Read-only, computed from the job version history so each event is reported once.
    """
    try:
        return build_change_summary(db, days=days, limit=limit)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="The API cannot read the job change history.",
        ) from exc


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
    role_scope: Literal["software_engineering", "all"] = Query(default="software_engineering"),
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

        if role_scope == "software_engineering" and not _is_target_software_role(job.title):
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
    role_scope: Literal["software_engineering", "all"] = Query(default="software_engineering"),
    compensation_filter: Literal["target_or_unknown", "target_only", "all"] = Query(default="target_or_unknown"),
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

        if role_scope == "software_engineering" and not _is_target_software_role(job.title):
            continue

        compensation = _compensation_signal(job.description or "")
        if compensation_filter == "target_only" and compensation["status"] not in {"target_25_to_30", "target_30_plus"}:
            continue
        if compensation_filter == "target_or_unknown" and compensation["status"] == "below_target":
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
                "compensation": _compensation_signal(job.description or ""),
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
            "role_scope": role_scope,
            "compensation_filter": compensation_filter,
            "target_compensation_floor_lpa": TARGET_COMPENSATION_FLOOR_LPA,
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


@app.get("/api/recommendations")
def recommendations(
    limit: int = Query(20, ge=1, le=50, description="How many opportunities to return."),
    sort: Literal["opportunity", "score", "newest", "company", "location", "experience", "salary"] = "opportunity",
    include_skip: bool = Query(False, description="Also list jobs whose next action is Skip."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """The best current opportunities with a next action, plus the skill gaps they share.

    Candidates are active software jobs in India that fit the early-career policy. The rule-based
    match and eligibility decide the action; freshness, company priority and disclosed pay only rank.
    """
    ensure_match_cache_table(db.get_bind())
    rows = db.execute(
        select(Job, Company).join(Company, Company.id == Job.company_id).where(Job.is_active.is_(True))
    ).all()
    candidates = [
        (job, company_obj, _find_matching_location(job.location, "India"))
        for job, company_obj in rows
        if _is_target_software_role(job.title)
        and _is_early_career_suitable(job.title, job.description or "")
        and _find_matching_location(job.location, "India") is not None
    ]

    profile = _candidate_profile()
    profile_hash = profile_fingerprint(profile)
    cached = load_cached_matches(db, [job for job, _, _ in candidates], profile_hash)
    matcher: JobMatcher | None = None
    try:
        priorities = {str(c.get("name")): c.get("priority") for c in load_registry_companies()}
    except (OSError, ValueError):
        priorities = {}

    items: list[dict[str, Any]] = []
    for job, company_obj, matched_location in candidates:
        match_data = cached.get(int(job.id))
        if match_data is None:
            matcher = matcher or JobMatcher(candidate_profile=profile)
            match_data = _serialize_match(matcher.match(job))
            save_cached_match(db, job, profile_hash, match_data)
        compensation = _compensation_signal(job.description or "")
        opportunity = score_opportunity(
            match=match_data,
            posted_at=job.posted_at,
            first_seen_at=job.first_seen_at,
            company_priority=priorities.get(company_obj.name),
            compensation=compensation,
        )
        items.append({
            "id": job.id,
            "title": job.title,
            "company": company_obj.name,
            "location": matched_location,
            "url": job.url,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "first_seen_at": job.first_seen_at.isoformat() if job.first_seen_at else None,
            "match_score": match_data.get("score"),
            "match_recommendation": match_data.get("recommendation_label"),
            "required_years": match_data.get("required_years"),
            "missing_required_skills": list(match_data.get("missing_required_skills") or []),
            "matched_required_skills": list(match_data.get("matched_required_skills") or []),
            "mismatches": match_data.get("mismatches") or {},
            "eligibility": match_data.get("eligibility") or {},
            "compensation": compensation,
            **opportunity,
        })
    db.commit()

    by_action = {action: 0 for action in OPPORTUNITY_ACTIONS}
    for item in items:
        by_action[item["action"]] += 1
    gap = skill_gap_report(items)

    visible = items if include_skip else [item for item in items if item["action"] != "skip"]
    sort_keys: dict[str, Any] = {
        "opportunity": lambda i: (-i["opportunity_score"], i["id"]),
        "score": lambda i: (-(i["match_score"] or 0), i["id"]),
        "newest": lambda i: (i["posted_at"] or i["first_seen_at"] or "", i["id"]),
        "company": lambda i: (i["company"].lower(), -i["opportunity_score"]),
        "location": lambda i: ((i["location"] or "").lower(), -i["opportunity_score"]),
        "experience": lambda i: (i["required_years"] is None, i["required_years"] or 0, -i["opportunity_score"]),
        "salary": lambda i: (i["compensation"].get("min_lpa") is None, -(i["compensation"].get("min_lpa") or 0), -i["opportunity_score"]),
    }
    visible.sort(key=sort_keys[sort], reverse=(sort == "newest"))
    return {
        "items": visible[:limit],
        "sort": sort,
        "summary": {"considered": len(items), "by_action": by_action, "shown": min(limit, len(visible))},
        "skill_gap": gap,
    }


@app.get("/api/jobs/compare")
def compare_jobs(
    ids: str = Query(..., description="Comma-separated job ids, 2 to 4 (for example 12,15,40)."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Compare several jobs side by side using their match data (computed and cached if missing)."""
    try:
        job_ids = list(dict.fromkeys(int(part) for part in ids.split(",") if part.strip()))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="ids must be comma-separated integers.") from exc
    if not 2 <= len(job_ids) <= 4:
        raise HTTPException(status_code=422, detail="Choose between 2 and 4 different jobs to compare.")

    ensure_match_cache_table(db.get_bind())
    jobs = {job.id: job for job in db.scalars(select(Job).where(Job.id.in_(job_ids))).all()}
    missing = [job_id for job_id in job_ids if job_id not in jobs]
    if missing:
        raise HTTPException(status_code=404, detail=f"Job(s) not found: {', '.join(map(str, missing))}.")

    profile = _candidate_profile()
    profile_hash = profile_fingerprint(profile)
    cached = load_cached_matches(db, list(jobs.values()), profile_hash)
    matcher: JobMatcher | None = None
    entries: list[dict[str, Any]] = []
    for job_id in job_ids:
        job = jobs[job_id]
        match_data = cached.get(job_id)
        if match_data is None:
            matcher = matcher or JobMatcher(candidate_profile=profile)
            match_data = _serialize_match(matcher.match(job))
            save_cached_match(db, job, profile_hash, match_data)
        company_obj = db.get(Company, job.company_id)
        entries.append({
            "id": job.id,
            "title": job.title,
            "company": company_obj.name if company_obj else None,
            "location": job.location,
            "url": job.url,
            "compensation": _compensation_signal(job.description or ""),
            "match": match_data,
        })
    db.commit()
    return build_comparison(entries)


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
# Optional local-AI job-description analysis
# ---------------------------------------------------------------------

@app.get("/api/ai/status")
def ai_status() -> dict[str, Any]:
    """Report which AI provider is selected and whether it is usable (non-throwing)."""
    try:
        return get_provider().status()
    except ValueError as exc:
        return {"provider": None, "available": False, "message": str(exc)}


@app.post("/api/jobs/{job_id}/ai-fit")
def ai_job_fit(
    job_id: int,
    refresh: bool = Query(False, description="Ignore the cached AI answer and ask the model again."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Explain how the candidate fits this job.

    The rule-based match and eligibility are authoritative. A local model, when available,
    adds a validated opinion; without one the same structure is built from the rules alone.
    """
    ensure_match_cache_table(db.get_bind())
    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} was not found.")
    company_obj = db.get(Company, job.company_id)

    profile = _candidate_profile()
    profile_hash = profile_fingerprint(profile)
    matcher = JobMatcher(candidate_profile=profile)
    cached = load_cached_matches(db, [job], profile_hash)
    if job_id in cached:
        match_data = cached[job_id]
    else:
        match_data = _serialize_match(matcher.match(job))
        save_cached_match(db, job, profile_hash, match_data)
        db.commit()

    description = job.description or ""
    ai_info: dict[str, Any]
    ai_fit: dict[str, Any] | None = None
    if len(description.strip()) < 40:
        ai_info = {"status": "skipped", "error": "The job description is too short for AI analysis."}
    else:
        try:
            provider = get_provider()
        except ValueError as exc:
            provider = None
            ai_info = {"status": "unavailable", "error": str(exc)}
        if provider is not None:
            skills = matcher.candidate_skill_set()
            job_text = job.title + chr(10) + description
            run = run_structured(
                task="candidate_fit",
                prompt_version=FIT_PROMPT_VERSION,
                prompt=build_fit_prompt(
                    title=job.title, company=company_obj.name if company_obj else None, description=description,
                    profile_skills=skills, candidate_years=_candidate_experience_years(), match=match_data,
                ),
                schema=FIT_SCHEMA,
                system=FIT_SYSTEM_PROMPT,
                validate=make_fit_validator(job_text=job_text, profile_skills=skills),
                cache_parts={"job": job_text, "profile": profile_hash},
                session=db,
                use_cache=not refresh,
            )
            ai_fit = run.result
            ai_info = {"status": run.status, "cached": run.cached, "provider": run.provider, "model": run.model,
                       "prompt_version": run.prompt_version, "attempts": run.attempts, "error": run.error}

    return {"job_id": job.id, "fit": merge_fit(ai_fit, match_data), "ai": ai_info}


@app.post("/api/jobs/{job_id}/ai-analysis")
def analyze_job_with_local_ai(
    job_id: int,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Run on-demand LLM extraction beside the deterministic JD analysis.

    This endpoint does not alter the job, candidate profile, match cache, or
    resume. The deterministic analyzer remains the baseline/source of truth.
    """
    job = db.scalar(select(Job).where(Job.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} was not found.")
    company_obj = db.get(Company, job.company_id)
    if company_obj is None:
        raise HTTPException(status_code=500, detail="The job refers to a missing company record.")
    if not job.description or len(job.description.strip()) < 40:
        raise HTTPException(status_code=422, detail="This job does not have enough description text for AI analysis.")

    deterministic = analyze_job_description_rules(
        title=job.title,
        description=job.description,
        location=job.location,
        employment_type=job.employment_type,
    )
    try:
        ai_result = analyze_job_description_with_ollama(
            title=job.title,
            description=job.description,
            location=job.location,
            employment_type=job.employment_type,
            required_years_evidence=deterministic.required_years_min,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OllamaModelNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OllamaUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OllamaError as exc:
        logger.exception("Local AI job analysis failed for job %s", job_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "job": {
            "id": job.id,
            "title": job.title,
            "company": company_obj.name,
            "location": job.location,
            "source": job.source,
        },
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "deterministic_analysis": deterministic.to_dict(),
        "ai_analysis": ai_result["insights"],
        "input": {
            "source_characters": ai_result["source_characters"],
            "truncated": ai_result["input_truncated"],
        },
        "grounding_note": ai_result["grounding_note"],
        "persisted": False,
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
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    company_name: str | None = None
    if request.job_id is not None:
        linked_job = db.get(Job, request.job_id)
        if linked_job is None:
            raise HTTPException(status_code=404, detail=f"Job with ID {request.job_id} was not found.")
        linked_company = db.get(Company, linked_job.company_id)
        company_name = linked_company.name if linked_company else None

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
    # Seconds alone are not unique: two generations in the same second would share a name, and
    # cleaning up a refused one would delete the other's files. A random suffix prevents that.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + os.urandom(3).hex()
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
        # Fail closed: every bullet must be text of a verified, selected evidence record.
        fabrication = fabrication_check(output_path, store_data, selection)
        if not fabrication["ok"]:
            raise FabricationError(
                "the document contains text that is not backed by your verified evidence: "
                + "; ".join(fabrication["violations"][:3])
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

    report = build_tailoring_report(selection, store_data)
    ResumeVersion.__table__.create(bind=db.get_bind(), checkfirst=True)
    version = ResumeVersion(
        job_id=request.job_id,
        job_title=request.job_title,
        company_name=company_name,
        docx_filename=filename,
        pdf_filename=pdf_filename,
        audit_filename=audit_path.name,
        evidence_count=len(selection["selected_evidence"]),
        report_json=json.dumps(report, ensure_ascii=False),
        evaluation_json=json.dumps(evaluation, ensure_ascii=False, default=str),
        fabrication_json=json.dumps(fabrication, ensure_ascii=False),
    )
    db.add(version)
    db.commit()

    return {
        "status": "created",
        "version_id": version.id,
        "report": report,
        "fabrication_check": fabrication,
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


# ---------------------------------------------------------------------
# Cover letters and employer-answer library (verified facts only)
# ---------------------------------------------------------------------

class CoverLetterGenerateRequest(BaseModel):
    job_id: int = Field(gt=0)


class CoverLetterEditRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class AnswerDraftRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    question_key: str | None = Field(default=None, description="Skip detection and force a question type.")
    job_id: int | None = Field(default=None, gt=0)
    technology: str | None = Field(default=None, max_length=80)


class AnswerEditRequest(BaseModel):
    answer: str = Field(max_length=5000)


class AnswerApproveRequest(BaseModel):
    confirm: bool = Field(default=False, description="Required for sensitive and company-specific answers.")


def _ensure_document_tables(db: Session) -> None:
    for table in (CoverLetterVersion.__table__, EmployerAnswer.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def _job_context(db: Session, job_id: int) -> tuple[Job, str | None, dict[str, Any] | None, list[str]]:
    """Job, its company name, verified-evidence selection (None if unavailable) and required skills."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} was not found.")
    company_obj = db.get(Company, job.company_id)
    company_name = company_obj.name if company_obj else None
    required: list[str] = []
    try:
        required = list(_serialize_match(JobMatcher(candidate_profile=_candidate_profile()).match(job)).get("required_skills") or [])
    except Exception:  # noqa: BLE001 - a matcher problem must not block a draft
        required = []
    selection: dict[str, Any] | None = None
    description = job.description or ""
    if len(description.strip()) >= 20:
        try:
            selection = _select_evidence(EvidenceSelectionRequest(
                job_title=job.title, job_description=description[:80000], required_skills=required[:100]))
        except HTTPException:
            selection = None  # evidence store missing: the draft then makes no skill or project claims
    return job, company_name, selection, required


def _cover_letter_dict(version: CoverLetterVersion, *, include_body: bool = True) -> dict[str, Any]:
    data = {
        "id": version.id,
        "job_id": version.job_id,
        "version_no": version.version_no,
        "source": version.source,
        "based_on_version_id": version.based_on_version_id,
        "job_title": version.job_title,
        "company_name": version.company_name,
        "saved_filename": version.saved_filename,
        "created_at": version.created_at.isoformat(),
        "report": json.loads(version.facts_json or "{}"),
    }
    if include_body:
        data["body"] = version.body
    return data


def _next_cover_letter_version(db: Session, job_id: int) -> int:
    return int(db.scalar(select(func.coalesce(func.max(CoverLetterVersion.version_no), 0)).where(CoverLetterVersion.job_id == job_id)) or 0) + 1


@app.post("/api/cover-letters/generate", status_code=201)
def generate_cover_letter_endpoint(request: CoverLetterGenerateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Draft a cover letter from verified facts only; edit it afterwards (each edit is a new version)."""
    _ensure_document_tables(db)
    job, company_name, selection, required = _job_context(db, request.job_id)
    letter = generate_cover_letter(
        job={"title": job.title, "company": company_name},
        facts=load_profile_facts(db),
        selection=selection,
        required_skills=required,
    )
    version = CoverLetterVersion(
        job_id=job.id, version_no=_next_cover_letter_version(db, job.id), source="template", job_title=job.title,
        company_name=company_name, body=letter["body"],
        facts_json=json.dumps({k: letter[k] for k in ("facts_used", "evidence_used", "not_claimed", "warnings")}, ensure_ascii=False),
    )
    db.add(version)
    db.commit()
    return _cover_letter_dict(version)


@app.get("/api/cover-letters")
def list_cover_letters(job_id: int | None = Query(None), db: Session = Depends(get_db)) -> dict[str, Any]:
    _ensure_document_tables(db)
    statement = select(CoverLetterVersion).order_by(CoverLetterVersion.created_at.desc(), CoverLetterVersion.id.desc()).limit(100)
    if job_id is not None:
        statement = statement.where(CoverLetterVersion.job_id == job_id)
    return {"items": [_cover_letter_dict(v, include_body=False) for v in db.scalars(statement).all()]}


def _get_cover_letter(db: Session, version_id: int) -> CoverLetterVersion:
    _ensure_document_tables(db)
    version = db.get(CoverLetterVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Cover letter version {version_id} was not found.")
    return version


@app.get("/api/cover-letters/{version_id}")
def get_cover_letter(version_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    return _cover_letter_dict(_get_cover_letter(db, version_id))


@app.post("/api/cover-letters/{version_id}/edit", status_code=201)
def edit_cover_letter(version_id: int, request: CoverLetterEditRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Save the user's edit as a NEW version; earlier versions are kept."""
    base = _get_cover_letter(db, version_id)
    body = request.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="The cover letter cannot be empty.")
    version = CoverLetterVersion(
        job_id=base.job_id, version_no=_next_cover_letter_version(db, base.job_id), source="user_edit",
        based_on_version_id=base.id, job_title=base.job_title, company_name=base.company_name, body=body,
        facts_json=base.facts_json,
    )
    db.add(version)
    db.commit()
    return _cover_letter_dict(version)


@app.get("/api/cover-letters/{version_id}/download")
def download_cover_letter(version_id: int, format: Literal["docx", "pdf"] = "docx", db: Session = Depends(get_db)) -> Response:
    version = _get_cover_letter(db, version_id)
    title = f"Cover letter - {version.job_title}"
    if format == "pdf":
        content, media = cover_letter_pdf(version.body, title), "application/pdf"
    else:
        content = cover_letter_docx(version.body, title)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", version.job_title).strip("_")[:50] or "Job"
    return Response(content=content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="CoverLetter_{slug}_v{version.version_no}.{format}"'})


@app.post("/api/cover-letters/{version_id}/save-file")
def save_cover_letter_file(version_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Write the DOCX next to the generated resumes so an application can reference it."""
    version = _get_cover_letter(db, version_id)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", version.job_title).strip("_")[:50] or "Job"
    filename = f"CoverLetter_{slug}_v{version.version_no}_{version.id}.docx"
    GENERATED_RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    (GENERATED_RESUMES_DIR / filename).write_bytes(cover_letter_docx(version.body, f"Cover letter - {version.job_title}"))
    version.saved_filename = filename
    db.commit()
    return {"filename": filename, "usable_as_application_cover_letter": True}


def _answer_dict(answer: EmployerAnswer) -> dict[str, Any]:
    return {
        "id": answer.id, "question_key": answer.question_key, "question": answer.question, "answer": answer.answer,
        "status": answer.status, "sensitive": answer.sensitive, "company_specific": answer.company_specific,
        "job_id": answer.job_id, "company_name": answer.company_name, "facts_used": json.loads(answer.facts_used or "[]"),
        "message": answer.message, "approved_at": answer.approved_at.isoformat() if answer.approved_at else None,
        "created_at": answer.created_at.isoformat(), "updated_at": answer.updated_at.isoformat(),
    }


def _get_answer(db: Session, answer_id: int) -> EmployerAnswer:
    _ensure_document_tables(db)
    answer = db.get(EmployerAnswer, answer_id)
    if answer is None:
        raise HTTPException(status_code=404, detail=f"Answer {answer_id} was not found.")
    return answer


@app.post("/api/answers/draft", status_code=201)
def draft_employer_answer(request: AnswerDraftRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Draft an answer from verified facts. Missing facts are reported, never invented."""
    _ensure_document_tables(db)
    key = request.question_key or classify_question(request.question)
    if key not in ANSWER_QUESTION_KEYS:
        raise HTTPException(status_code=422, detail=f"question_key must be one of: {', '.join(ANSWER_QUESTION_KEYS)}.")
    job_info: dict[str, Any] | None = None
    selection: dict[str, Any] | None = None
    company_name: str | None = None
    if request.job_id is not None:
        job, company_name, selection, _ = _job_context(db, request.job_id)
        job_info = {"title": job.title, "company": company_name}
    try:
        evidence = [r for r in _load_evidence_store().get("evidence", []) if (r.get("review") or {}).get("user_verified") is True]
    except HTTPException:
        evidence = []
    matched = list(((selection or {}).get("coverage") or {}).get("verified_covered") or [])
    draft = draft_answer(key, facts=load_profile_facts(db), job=job_info, evidence=evidence,
                         technology=request.technology, matched_skills=matched)
    now = datetime.utcnow()
    row = EmployerAnswer(
        question_key=key, question=request.question.strip(), answer=draft["answer"], status=draft["status"],
        sensitive=draft["sensitive"], company_specific=draft["company_specific"], job_id=request.job_id,
        company_name=company_name, facts_used=json.dumps(draft["facts_used"]), message=draft["message"],
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.commit()
    return _answer_dict(row)


@app.get("/api/answers")
def list_employer_answers(
    status: Literal["needs_input", "draft", "approved"] | None = None,
    question_key: str | None = None,
    job_id: int | None = None,
    reusable: bool = Query(False, description="Only approved answers that are not tied to one job."),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _ensure_document_tables(db)
    statement = select(EmployerAnswer).order_by(EmployerAnswer.updated_at.desc(), EmployerAnswer.id.desc()).limit(200)
    if reusable:
        statement = statement.where(EmployerAnswer.status == "approved", EmployerAnswer.job_id.is_(None))
    if status:
        statement = statement.where(EmployerAnswer.status == status)
    if question_key:
        statement = statement.where(EmployerAnswer.question_key == question_key)
    if job_id is not None:
        statement = statement.where(EmployerAnswer.job_id == job_id)
    return {"items": [_answer_dict(a) for a in db.scalars(statement).all()]}


@app.patch("/api/answers/{answer_id}")
def edit_employer_answer(answer_id: int, request: AnswerEditRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Edit the text. Any edit withdraws a previous approval; approve again afterwards."""
    answer = _get_answer(db, answer_id)
    answer.answer = request.answer.strip()
    answer.status = "needs_input" if (not answer.answer or unresolved_answer_placeholders(answer.answer)) else "draft"
    answer.approved_at = None
    answer.updated_at = datetime.utcnow()
    db.commit()
    return _answer_dict(answer)


@app.post("/api/answers/{answer_id}/approve")
def approve_employer_answer(answer_id: int, request: AnswerApproveRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    answer = _get_answer(db, answer_id)
    blockers = answer_approval_blockers(answer=answer.answer, sensitive=answer.sensitive,
                                        company_specific=answer.company_specific, confirm=request.confirm)
    if blockers:
        raise HTTPException(status_code=409, detail=" ".join(blockers))
    answer.status = "approved"
    answer.approved_at = datetime.utcnow()
    answer.updated_at = answer.approved_at
    db.commit()
    return _answer_dict(answer)


@app.delete("/api/answers/{answer_id}", status_code=204)
def delete_employer_answer(answer_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_get_answer(db, answer_id))
    db.commit()


def _resume_version_summary(version: ResumeVersion) -> dict[str, Any]:
    evaluation = json.loads(version.evaluation_json or "{}")
    return {
        "id": version.id,
        "job_id": version.job_id,
        "job_title": version.job_title,
        "company_name": version.company_name,
        "created_at": version.created_at.isoformat(),
        "evidence_count": version.evidence_count,
        "readiness_label": evaluation.get("readiness_label"),
        "docx_filename": version.docx_filename,
        "pdf_filename": version.pdf_filename,
        "download_url": f"/api/resumes/{version.docx_filename}/download",
        "pdf_download_url": f"/api/resumes/{version.pdf_filename}/download",
        "files_present": {
            "docx": (GENERATED_RESUMES_DIR / version.docx_filename).is_file(),
            "pdf": (GENERATED_RESUMES_DIR / version.pdf_filename).is_file(),
        },
    }


@app.get("/api/resume-versions")
def list_resume_versions(
    job_id: int | None = Query(None, description="Only versions generated for this job."),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generated tailored resumes, newest first (the master resume is never listed or changed)."""
    ResumeVersion.__table__.create(bind=db.get_bind(), checkfirst=True)
    statement = select(ResumeVersion).order_by(ResumeVersion.created_at.desc(), ResumeVersion.id.desc()).limit(limit)
    if job_id is not None:
        statement = statement.where(ResumeVersion.job_id == job_id)
    versions = db.scalars(statement).all()
    return {"items": [_resume_version_summary(version) for version in versions], "total": len(versions)}


@app.get("/api/resume-versions/{version_id}")
def get_resume_version(version_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """One version with its tailoring report, quality checks and no-fabrication result."""
    ResumeVersion.__table__.create(bind=db.get_bind(), checkfirst=True)
    version = db.get(ResumeVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Resume version {version_id} was not found.")
    return {
        **_resume_version_summary(version),
        "report": json.loads(version.report_json),
        "evaluation": json.loads(version.evaluation_json),
        "fabrication_check": json.loads(version.fabrication_json),
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
