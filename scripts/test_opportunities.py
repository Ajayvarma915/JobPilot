"""Tests for opportunity scoring, next actions, skill gaps and GET /api/recommendations (temp DB)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_opportunities.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.services.opportunities import (  # noqa: E402
    APPLY_NOW, PREPARE_MISSING_SKILLS, REVIEW_FIRST, SKIP, decide_action, score_opportunity, skill_gap_report,
)
from scripts.test_structured_job_matching import build_candidate_profile  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _match(score=80.0, recommendation="strong_match", eligibility="eligible", mandatory=(), experience=(), reasons=()):
    return {"score": score, "recommendation": recommendation,
            "eligibility": {"status": eligibility, "reasons": list(reasons)},
            "mismatches": {"mandatory_requirement_mismatch": list(mandatory), "experience_mismatch": list(experience)}}


def test_actions_follow_the_rules() -> None:
    check(decide_action(_match())[0] == APPLY_NOW, "clean strong match -> apply now")
    check(decide_action(_match(eligibility="excluded", reasons=["senior_or_lead_title"], score=90))[0] == SKIP, "excluded -> skip even at 90")
    check(decide_action(_match(score=30, recommendation="low_match"))[0] == SKIP, "low match -> skip")
    check(decide_action(_match(score=70, mandatory=["Missing required skill: Docker"]))[0] == PREPARE_MISSING_SKILLS, "gap + decent match -> prepare")
    check(decide_action(_match(score=40, recommendation="review", mandatory=["Missing required skill: Docker"]))[0] == SKIP, "gap + weak match -> skip")
    check(decide_action(_match(eligibility="eligible_needs_review"))[0] == REVIEW_FIRST, "needs review -> review first")
    check(decide_action(_match(score=50, recommendation="review"))[0] == REVIEW_FIRST, "borderline -> review first")
    check(decide_action(_match(experience=["Asks for 2 years; the profile shows 1"]))[0] == REVIEW_FIRST, "experience gap -> review first")
    for _, reasons in (decide_action(_match()), decide_action(_match(score=30, recommendation="low_match"))):
        check(reasons, "every action carries a reason")


def test_scoring_signals() -> None:
    now = datetime(2026, 11, 16)
    fresh = score_opportunity(match=_match(), posted_at=now - timedelta(days=1), company_priority=1,
                              compensation={"status": "target_30_plus"}, now=now)
    stale = score_opportunity(match=_match(), posted_at=now - timedelta(days=90), company_priority=3,
                              compensation={"status": "not_disclosed"}, now=now)
    check(fresh["opportunity_score"] > stale["opportunity_score"], "fresher, higher-priority ranks higher")
    check(sum(fresh["weights"].values()) == 100.0, "weights add to 100")
    undisclosed = score_opportunity(match=_match(), posted_at=now, company_priority=1, compensation={"status": "not_disclosed"}, now=now)
    below = score_opportunity(match=_match(), posted_at=now, company_priority=1, compensation={"status": "below_target"}, now=now)
    check(undisclosed["components"]["compensation"] == 50.0 and below["components"]["compensation"] == 50.0, "pay never changes the score")
    check(any("does not affect ranking" in s for s in undisclosed["signals"]), "the neutral treatment is stated")
    unknown_date = score_opportunity(match=_match(), now=now)
    check(any("unknown" in s.lower() for s in unknown_date["signals"]), "unknown dates are reported")
    skipped = score_opportunity(match=_match(eligibility="excluded", reasons=["x"], score=95), posted_at=now, company_priority=1,
                                compensation={"status": "target_30_plus"}, now=now)
    check(skipped["action"] == SKIP and skipped["opportunity_score"] <= 30.0, "a skipped job can never out-rank a viable one")
    check("application deadline" in skipped["not_modelled"], "what is not modelled is stated")


def test_skill_gap_report() -> None:
    items = [
        {"action": APPLY_NOW, "title": "A", "company": "X", "missing_required_skills": []},
        {"action": PREPARE_MISSING_SKILLS, "title": "B", "company": "X", "missing_required_skills": ["Docker", "Kubernetes"]},
        {"action": REVIEW_FIRST, "title": "C", "company": "Y", "missing_required_skills": ["Docker"]},
        {"action": SKIP, "title": "D", "company": "Z", "missing_required_skills": ["Docker", "Haskell"]},
    ]
    report = skill_gap_report(items)
    check(report["jobs_considered"] == 3, "skipped jobs are not counted")
    gaps = {g["skill"]: g for g in report["gaps"]}
    check(gaps["Docker"]["jobs_requiring"] == 2 and "Haskell" not in gaps, f"{gaps}")
    check(gaps["Docker"]["share_of_jobs"] == 0.67 and gaps["Docker"]["companies"] == ["X", "Y"], f"{gaps['Docker']}")
    check(report["small_sample"] is True and "only 3" in report["note"], "small samples are flagged")
    check(report["learning_plan"][0]["skill"] == "Docker" and "only once you have" in report["learning_plan"][0]["step"], "plan never tells you to claim skills")
    check(skill_gap_report([])["gaps"] == [], "empty input -> empty report")


def test_recommendations_endpoint() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        jobs = (
            ("a", "Backend Engineer", "Hyderabad, India", "Minimum qualifications: 1 year of experience with software development using Java, Python."),
            ("b", "Platform Engineer", "Pune, India", "Minimum qualifications: 1 year of experience with software development using Java, Python, Docker, Kubernetes."),
            ("c", "Senior Staff Backend Engineer", "Hyderabad, India", "Minimum qualifications: 1 year of experience using Java, Python."),
            ("d", "Backend Engineer", "Seattle, WA, United States", "Minimum qualifications: 1 year of experience using Java, Python."),
        )
        ids = {}
        for key, title, location, description in jobs:
            ids[key] = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": key, "title": title, "location": [location],
                                                           "url": f"https://acme.example/{key}", "description": description}).job.id
        session.commit()
    finally:
        session.close()

    profile = build_candidate_profile()
    profile.years_of_experience = 1.2
    api_main._candidate_profile = lambda: profile
    client = TestClient(api_main.app)

    body = client.get("/api/recommendations").json()
    shown = {item["id"]: item for item in body["items"]}
    check(ids["c"] not in shown and ids["d"] not in shown, "senior roles and non-India jobs are not candidates")
    check(body["summary"]["considered"] == 2, f"only a and b are candidates: {body['summary']}")
    check(shown[ids["a"]]["action"] == APPLY_NOW, f"a: {shown[ids['a']]['action']} {shown[ids['a']]['reasons']}")
    check(shown[ids["b"]]["action"] == PREPARE_MISSING_SKILLS and "Docker" in shown[ids["b"]]["missing_required_skills"], f"b: {shown[ids['b']]}")
    check(body["items"][0]["id"] == ids["a"], "the clean fit ranks first by default")
    check(sum(body["summary"]["by_action"].values()) == 2, "summary counts every candidate")
    check({g["skill"] for g in body["skill_gap"]["gaps"]} >= {"Docker", "Kubernetes"} and body["skill_gap"]["small_sample"], "skill gaps computed from the stored jobs")
    for field in ("opportunity_score", "action_label", "reasons", "signals", "components", "url", "company", "mismatches"):
        check(field in shown[ids["a"]], f"missing field {field}")

    by_score = client.get("/api/recommendations", params={"sort": "score"}).json()["items"]
    check([i["match_score"] for i in by_score] == sorted([i["match_score"] for i in by_score], reverse=True), "sort=score is descending")
    by_exp = client.get("/api/recommendations", params={"sort": "experience"}).json()
    check(by_exp["sort"] == "experience" and len(by_exp["items"]) == 2, "other sorts work")
    check(len(client.get("/api/recommendations", params={"limit": 1}).json()["items"]) == 1, "limit respected")
    check(client.get("/api/recommendations", params={"sort": "bogus"}).status_code == 422, "unknown sort rejected")
    check(client.get("/api/recommendations", params={"limit": 500}).status_code == 422, "limit capped")


TESTS = [
    ("Next actions follow the rules", test_actions_follow_the_rules),
    ("Scoring signals and neutral undisclosed pay", test_scoring_signals),
    ("Skill-gap report counts only pursuable jobs", test_skill_gap_report),
    ("GET /api/recommendations", test_recommendations_endpoint),
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
