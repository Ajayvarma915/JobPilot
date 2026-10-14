from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.services.job_match_cache import (
    ensure_match_cache_table,
    job_fingerprint,
    load_cached_matches,
    profile_fingerprint,
    release_cache_warmup,
    reserve_cache_warmup,
    save_cached_match,
)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_job() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        company_id=7,
        external_id="example-job-1",
        title="Software Engineer",
        description="Build and maintain reliable software services.",
        location="Hyderabad, India",
        source="test-source",
        experience_level="Early",
        employment_type="Full-time",
    )


def test_persistent_cache_round_trip() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "INSERT INTO jobs (id) VALUES (1)"
            )

        ensure_match_cache_table(test_engine)

        job = make_job()
        profile = {
            "years_of_experience": 1.0,
            "target_role_families": ["software_engineering"],
        }
        profile_hash = profile_fingerprint(profile)

        expected = {
            "score": 86.5,
            "recommendation": "strong_match",
            "recommendation_label": "Strong match",
            "reasons": ["Role family matches a target role."],
            "concerns": [],
        }

        with Session(test_engine) as db:
            save_cached_match(db, job, profile_hash, expected)
            db.commit()

            cached = load_cached_matches(db, [job], profile_hash)

            check(
                cached.get(1) == expected,
                "A saved match result could not be loaded.",
            )

        # Open a new session to verify that the cache is persistent.
        with Session(test_engine) as db:
            cached = load_cached_matches(db, [job], profile_hash)
            check(
                cached.get(1) == expected,
                "The match result did not persist across sessions.",
            )

    finally:
        test_engine.dispose()


def test_stale_job_is_not_reused() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    try:
        with test_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE jobs (id INTEGER PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "INSERT INTO jobs (id) VALUES (1)"
            )

        ensure_match_cache_table(test_engine)

        job = make_job()
        profile_hash = profile_fingerprint({"years_of_experience": 1.0})

        with Session(test_engine) as db:
            save_cached_match(
                db,
                job,
                profile_hash,
                {"score": 75.0},
            )
            db.commit()

            job.description = (
                "Build distributed systems and scalable data pipelines."
            )

            cached = load_cached_matches(db, [job], profile_hash)

            check(
                1 not in cached,
                "A cache entry was incorrectly reused after a JD change.",
            )

    finally:
        test_engine.dispose()


def test_profile_fingerprint_changes() -> None:
    first = {
        "years_of_experience": 1.0,
        "target_role_families": ["software_engineering"],
    }
    identical = {
        "target_role_families": ["software_engineering"],
        "years_of_experience": 1.0,
    }
    changed = {
        "years_of_experience": 2.0,
        "target_role_families": ["software_engineering"],
    }

    check(
        profile_fingerprint(first) == profile_fingerprint(identical),
        "Equivalent candidate profiles should have the same fingerprint.",
    )
    check(
        profile_fingerprint(first) != profile_fingerprint(changed),
        "A changed candidate profile must invalidate the old cache.",
    )


def test_duplicate_warmup_reservation() -> None:
    profile_hash = "cache-test-profile"
    job_ids = [910001, 910002]

    first = reserve_cache_warmup(job_ids, profile_hash)
    second = reserve_cache_warmup(job_ids, profile_hash)

    try:
        check(
            first == job_ids,
            "The first reservation should include both job IDs.",
        )
        check(
            second == [],
            "Duplicate warm-up requests should not reserve the same jobs.",
        )
    finally:
        release_cache_warmup(first, profile_hash)

    third = reserve_cache_warmup(job_ids, profile_hash)

    try:
        check(
            third == job_ids,
            "Released job IDs should be reservable again.",
        )
    finally:
        release_cache_warmup(third, profile_hash)


def main() -> int:
    tests = [
        (
            "Persistent cache save/load",
            test_persistent_cache_round_trip,
        ),
        (
            "Stale job invalidation",
            test_stale_job_is_not_reused,
        ),
        (
            "Candidate profile fingerprint",
            test_profile_fingerprint_changes,
        ),
        (
            "Duplicate background warm-up prevention",
            test_duplicate_warmup_reservation,
        ),
    ]

    print("=" * 68)
    print("JobPilot Match Cache Tests")
    print("=" * 68)

    passed = 0
    failed = 0

    for number, (name, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {number}: PASS - {name}")
        except Exception as exc:
            failed += 1
            print(
                f"Test {number}: FAIL - {name}\n"
                f"  {type(exc).__name__}: {exc}"
            )

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: Match cache tests failed.")
        return 1

    print("SUCCESS: Match cache tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())