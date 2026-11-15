"""Tests for configurable weights, the eligibility cap, mismatch categories and job comparison."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_match_explainability.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.services import match_weights  # noqa: E402
from app.services.job_compare import build_comparison  # noqa: E402
from app.services.job_match_cache import profile_fingerprint  # noqa: E402
from app.services.job_matcher import JobMatcher  # noqa: E402
from scripts.test_structured_job_matching import build_candidate_profile  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _job(title="Software Engineer II", location="Hyderabad, Telangana, India", description=None):
    return SimpleNamespace(
        title=title, location=location, employment_type="Full-time",
        description=description or (
            "Minimum Qualifications\nBachelor's degree or equivalent practical experience.\n"
            "1 year of experience with software development in Java and Python.\n"
            "Experience with JavaScript.\n\nPreferred Qualifications\nExperience with React.js and Kubernetes.\n"
        ),
    )


def test_weights_validation() -> None:
    good = dict(match_weights.DEFAULT_WEIGHTS)
    check(match_weights.validate_match_weights(good) == good, "defaults are valid")
    for bad, fragment in (
        ({**good, "role": 30}, "add up to 100"),
        ({**good, "role": -5, "skills": 50}, "negative"),
        ({k: v for k, v in good.items() if k != "skills"}, "Missing"),
        ({**good, "luck": 1}, "Unknown"),
        ({**good, "role": "25"}, "number"),
        ([1, 2], "object"),
    ):
        try:
            match_weights.validate_match_weights(bad)
        except ValueError as exc:
            check(fragment.lower() in str(exc).lower(), f"expected '{fragment}' in: {exc}")
        else:
            raise AssertionError(f"invalid weights accepted: {bad}")
    path = Path(_TEMP_DIR.name) / "weights.json"
    check(match_weights.load_match_weights(path) == good, "missing file falls back to defaults")
    path.write_text(json.dumps({"weights": {**good, "role": 10, "skills": 35}}), encoding="utf-8")
    check(match_weights.load_match_weights(path)["skills"] == 35.0, "file weights are loaded")
    path.write_text("{broken", encoding="utf-8")
    try:
        match_weights.load_match_weights(path)
    except ValueError:
        pass
    else:
        raise AssertionError("a corrupt weights file must raise, not silently use defaults")
    check(match_weights.load_match_weights()["role"] == 25.0, "the shipped data/match_weights.json is valid")


def test_weights_change_the_score_and_cache_key() -> None:
    profile = build_candidate_profile()
    default = JobMatcher(profile).match(_job())
    heavy_skills = {**match_weights.DEFAULT_WEIGHTS, "role": 10.0, "skills": 35.0}
    shifted = JobMatcher(profile, weights=heavy_skills).match(_job())
    check(shifted.weights_used["skills"] == 35.0, "weights echoed in the result")
    check(abs(shifted.skills_score - default.skills_score * 35.0 / 20.0) < 0.05, "skills component rescaled by its weight")
    check(abs(shifted.role_score - default.role_score * 10.0 / 25.0) < 0.05, "role component rescaled by its weight")
    check(shifted.score != default.score, "changing weights changes the score")
    check(shifted.score <= 100.0, "score stays within 100")

    zeroed = JobMatcher(profile, weights={**match_weights.DEFAULT_WEIGHTS, "location": 0.0, "role": 30.0}).match(_job())
    check(zeroed.location_score == 0.0, "a zero weight removes the component")

    original = match_weights.WEIGHTS_PATH
    try:
        key_default = profile_fingerprint(profile)
        path = Path(_TEMP_DIR.name) / "other_weights.json"
        path.write_text(json.dumps({"weights": heavy_skills}), encoding="utf-8")
        match_weights.WEIGHTS_PATH = path
        check(profile_fingerprint(profile) != key_default, "changing the weights must change the cache key")
    finally:
        match_weights.WEIGHTS_PATH = original


def test_eligibility_is_authoritative_over_keywords() -> None:
    profile = build_candidate_profile()
    strong_text = (
        "Minimum Qualifications\n1 year of experience with software development in Java and Python.\n"
        "Experience with JavaScript.\n\nPreferred Qualifications\nReact.js\n"
    )
    ok = JobMatcher(profile).match(_job(description=strong_text))
    check(ok.eligibility_status in {"eligible", "eligible_needs_review"} and not ok.eligibility_capped, f"{ok.eligibility_status}")

    senior = JobMatcher(profile).match(_job(title="Senior Staff Software Engineer", description=strong_text))
    check(senior.score <= JobMatcher.ELIGIBILITY_CAP, f"keyword overlap must not lift an excluded title: {senior.score}")
    check(senior.eligibility_status == "excluded" and senior.eligibility_reasons, "excluded with a reason")
    check(any("eligibility policy" in c for c in senior.concerns), "the concern says why")

    phd = JobMatcher(profile).match(_job(description="Minimum qualifications: PhD in Computer Science. Java Python JavaScript React."))
    check(phd.score <= 35.0 and phd.mismatches["mandatory_requirement_mismatch"], f"PhD is a mandatory mismatch: {phd.score}")

    wrong = JobMatcher(profile).match(_job(title="Account Executive", description=strong_text))
    check(wrong.score <= JobMatcher.ELIGIBILITY_CAP, "a non-engineering title is capped however many skills match")


def test_mismatch_categories() -> None:
    profile = build_candidate_profile()
    result = JobMatcher(profile).match(_job(
        location="Seattle, WA, United States",
        description=(
            "Minimum Qualifications\n4 years of experience with software development using Java, Python, Go, Docker.\n\n"
            "Preferred Qualifications\nKubernetes experience.\n"
        ),
    ))
    m = result.mismatches
    check(set(m) == {"mandatory_requirement_mismatch", "preferred_skill_missing", "experience_mismatch",
                     "location_mismatch", "seniority_mismatch"}, f"categories: {sorted(m)}")
    check(any("Docker" in item for item in m["mandatory_requirement_mismatch"]), f"missing required skill listed: {m}")
    check(any("Kubernetes" in item for item in m["preferred_skill_missing"]), f"missing preferred skill listed: {m}")
    check(m["experience_mismatch"] and "4" in m["experience_mismatch"][0], f"experience mismatch: {m['experience_mismatch']}")
    check(m["location_mismatch"], "location mismatch reported separately")
    experienced = build_candidate_profile()
    experienced.years_of_experience = 1.2  # the API derives this from the TCS start date
    clean = JobMatcher(experienced).match(_job())
    check(not clean.mismatches["experience_mismatch"] and not clean.mismatches["location_mismatch"], "no false mismatches on a good fit")


def test_compare_endpoint_and_builder() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        ids = []
        for i, (title, desc) in enumerate((
            ("Backend Engineer", "Minimum qualifications: 1 year of experience with software development using Java, Python."),
            ("Platform Engineer", "Minimum qualifications: 1 year of experience with software development using Java, Python, Go, Docker."),
            ("Frontend Engineer", "Minimum qualifications: 1 year of experience with software development using JavaScript, React, Docker."),
        )):
            result = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": str(i), "title": title,
                                                         "location": ["Hyderabad, India"], "url": f"https://acme.example/{i}",
                                                         "description": desc})
            ids.append(result.job.id)
        session.commit()
    finally:
        session.close()

    client = TestClient(api_main.app)
    api_main._candidate_profile = lambda: build_candidate_profile()
    response = client.get("/api/jobs/compare", params={"ids": f"{ids[0]},{ids[1]}"})
    check(response.status_code == 200, response.text)
    body = response.json()
    check([j["id"] for j in body["jobs"]] == [ids[0], ids[1]], "rows keep the requested order")
    check(all(isinstance(j["score"], (int, float)) for j in body["jobs"]), "each row has a score")
    check(body["highlights"]["best_overall_job_id"] in ids[:2], "best job identified")
    skills = {item["skill"].lower(): item for item in body["highlights"]["skill_matrix"]}
    check("docker" in skills and skills["docker"]["covered_by_profile"] == 0, f"Docker is not in the profile: {list(skills)}")
    check("docker" in [s.lower() for s in body["highlights"]["skills_missing_everywhere"]], "gap listed")

    for params, status in (({"ids": str(ids[0])}, 422), ({"ids": "1,2,3,4,5"}, 422), ({"ids": "a,b"}, 422),
                           ({"ids": f"{ids[0]},{ids[0]}"}, 422), ({"ids": f"{ids[0]},9999"}, 404)):
        check(client.get("/api/jobs/compare", params=params).status_code == status, f"{params} -> {status}")

    single = build_comparison([
        {"id": 1, "title": "A", "company": "X", "match": {"score": 80, "required_skills": ["Java"], "matched_required_skills": ["java"]}},
        {"id": 2, "title": "B", "company": "Y", "match": {"score": 50, "required_skills": ["Java", "Go"], "matched_required_skills": ["Java"],
                                                          "eligibility": {"status": "excluded", "reasons": ["senior_or_lead_title"]}}},
    ])
    check(single["highlights"]["best_overall_job_id"] == 1 and single["highlights"]["jobs_with_blockers"] == [2], "blockers flagged")
    try:
        build_comparison([{"id": 1, "title": "A", "company": "X", "match": {}}])
    except ValueError:
        pass
    else:
        raise AssertionError("one job is not a comparison")


TESTS = [
    ("Weights are validated", test_weights_validation),
    ("Weights change the score and the cache key", test_weights_change_the_score_and_cache_key),
    ("Eligibility is authoritative over keyword overlap", test_eligibility_is_authoritative_over_keywords),
    ("Mismatch categories are separate", test_mismatch_categories),
    ("Job comparison endpoint", test_compare_endpoint_and_builder),
]


def main() -> int:
    failed = 0
    for name, test in TESTS:
        try:
            test()
            print(f"PASS - {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL - {name}: {type(exc).__name__}: {exc}")
    engine.dispose()
    api_main.engine.dispose()
    _TEMP_DIR.cleanup()
    print(f"\nUnit tests: {len(TESTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
