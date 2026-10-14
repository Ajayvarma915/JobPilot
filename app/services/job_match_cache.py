from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import Engine, bindparam, text
from sqlalchemy.orm import Session


CACHE_VERSION = "jobpilot-match-cache-v1"
TABLE_NAME = "job_match_cache"

_init_lock = threading.Lock()
_initialized_engines: set[int] = set()

_warm_lock = threading.Lock()
_warming: set[tuple[int, str]] = set()


def ensure_match_cache_table(engine: Engine) -> None:
    """Create the cache table and index once for each database engine."""
    engine_id = id(engine)

    if engine_id in _initialized_engines:
        return

    with _init_lock:
        if engine_id in _initialized_engines:
            return

        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE IF NOT EXISTS job_match_cache (
                    job_id INTEGER PRIMARY KEY,
                    job_fingerprint TEXT NOT NULL,
                    profile_fingerprint TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_job_match_cache_profile_fingerprint
                ON job_match_cache(profile_fingerprint)
                """
            )

        _initialized_engines.add(engine_id)


def profile_fingerprint(profile: Any) -> str:
    """Return a stable fingerprint of the candidate profile."""
    if is_dataclass(profile):
        payload = asdict(profile)
    elif isinstance(profile, dict):
        payload = profile
    else:
        try:
            payload = vars(profile)
        except TypeError:
            payload = repr(profile)

    serialized = json.dumps(
        {
            "cache_version": CACHE_VERSION,
            "candidate_profile": payload,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def job_fingerprint(job: Any) -> str:
    """Hash the fields which can affect analysis and match scoring."""
    fields = {
        "cache_version": CACHE_VERSION,
        "id": getattr(job, "id", None),
        "company_id": getattr(job, "company_id", None),
        "external_id": getattr(job, "external_id", None),
        "title": getattr(job, "title", None),
        "description": getattr(job, "description", None),
        "location": getattr(job, "location", None),
        "source": getattr(job, "source", None),
        "experience_level": getattr(job, "experience_level", None),
        "employment_type": getattr(job, "employment_type", None),
    }

    serialized = json.dumps(
        fields,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_cached_matches(
    db: Session,
    jobs: Iterable[Any],
    profile_hash: str,
) -> dict[int, dict[str, Any]]:
    """
    Load valid cache entries in batches.

    Stale entries are treated as misses rather than returned.
    """
    job_list = list(jobs)
    cached: dict[int, dict[str, Any]] = {}

    if not job_list:
        return cached

    expected_fingerprints = {
        int(job.id): job_fingerprint(job)
        for job in job_list
        if getattr(job, "id", None) is not None
    }

    ids = list(expected_fingerprints)

    # Stay below SQLite's common bind-parameter limits.
    for start in range(0, len(ids), 500):
        batch = ids[start:start + 500]

        statement = text(
            """
            SELECT
                job_id,
                job_fingerprint,
                profile_fingerprint,
                result_json
            FROM job_match_cache
            WHERE job_id IN :job_ids
            """
        ).bindparams(bindparam("job_ids", expanding=True))

        rows = db.execute(
            statement,
            {"job_ids": batch},
        ).mappings().all()

        for row in rows:
            job_id = int(row["job_id"])

            if row["profile_fingerprint"] != profile_hash:
                continue

            if row["job_fingerprint"] != expected_fingerprints[job_id]:
                continue

            try:
                value = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                continue

            if isinstance(value, dict):
                cached[job_id] = value

    return cached


def save_cached_match(
    db: Session,
    job: Any,
    profile_hash: str,
    result: dict[str, Any],
) -> None:
    """Insert or replace one cached match result."""
    if getattr(job, "id", None) is None:
        raise ValueError("A persisted job ID is required for match caching.")

    serialized_result = json.dumps(
        result,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )

    db.execute(
        text(
            """
            INSERT INTO job_match_cache (
                job_id,
                job_fingerprint,
                profile_fingerprint,
                result_json,
                updated_at
            )
            VALUES (
                :job_id,
                :job_fingerprint,
                :profile_fingerprint,
                :result_json,
                :updated_at
            )
            ON CONFLICT(job_id) DO UPDATE SET
                job_fingerprint = excluded.job_fingerprint,
                profile_fingerprint = excluded.profile_fingerprint,
                result_json = excluded.result_json,
                updated_at = excluded.updated_at
            """
        ),
        {
            "job_id": int(job.id),
            "job_fingerprint": job_fingerprint(job),
            "profile_fingerprint": profile_hash,
            "result_json": serialized_result,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def reserve_cache_warmup(
    job_ids: Iterable[int],
    profile_hash: str,
) -> list[int]:
    """
    Reserve jobs for a warm-up task, avoiding overlapping tasks
    for the same job and profile.
    """
    reserved: list[int] = []

    with _warm_lock:
        for job_id in job_ids:
            key = (int(job_id), profile_hash)

            if key in _warming:
                continue

            _warming.add(key)
            reserved.append(int(job_id))

    return reserved


def release_cache_warmup(
    job_ids: Iterable[int],
    profile_hash: str,
) -> None:
    """Release warm-up reservations, including after a failed task."""
    with _warm_lock:
        for job_id in job_ids:
            _warming.discard((int(job_id), profile_hash))