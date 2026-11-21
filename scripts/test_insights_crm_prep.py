"""Tests for funnel analytics, the recruiter/referral contact book and interview preparation (temp DB)."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_insights_crm_prep.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.applications import crm  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.services.analytics import MIN_APPLIED_FOR_RATES, build_funnel  # noqa: E402
from scripts.test_structured_job_matching import build_candidate_profile  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _reset():
    # The tracker owns its own tables (not part of Base), so drop them too for a clean slate.
    with engine.begin() as connection:
        for table in ("application_status_history", "application_preparations", "applications", "candidate_profile_vault"):
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _make_jobs(count: int, company: str = "Acme", source: str = "lever:acme", description: str = "Minimum qualifications: 1 year of experience with software development using Java, Docker.") -> list[int]:
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company_row = repo.get_or_create_company(company)
        ids = [repo.upsert_job_detailed(company_row, {"source": source, "external_id": f"{company}-{i}", "title": f"Backend Engineer {i}",
                                                       "location": ["Pune, India"], "url": f"https://x.example/{company}/{i}",
                                                       "description": description}).job.id for i in range(count)]
        session.commit()
        return ids
    finally:
        session.close()


def test_funnel_counts_and_small_sample_rule() -> None:
    _reset()
    session = SessionLocal()
    try:
        empty = build_funnel(session)
        check(empty["counts"]["applied"] == 0 and empty["rates"] is None and "No applications" in empty["rates_hidden_reason"], "no applications -> zeros, no rates")
    finally:
        session.close()

    client = TestClient(api_main.app)
    ids = _make_jobs(3) + _make_jobs(1, company="Beta", source="greenhouse:beta")
    saved = client.post("/api/applications", json={"job_id": ids[0]}).json()
    applied = client.post("/api/applications", json={"job_id": ids[1], "status": "applied"}).json()
    interview = client.post("/api/applications", json={"job_id": ids[2], "status": "applied"}).json()
    client.patch(f"/api/applications/{interview['id']}", json={"status": "interview", "next_action": "Prep", "follow_up_date": (date.today() - timedelta(days=1)).isoformat()})
    rejected = client.post("/api/applications", json={"job_id": ids[3], "status": "applied"}).json()
    client.patch(f"/api/applications/{rejected['id']}", json={"status": "rejected"})
    client.patch(f"/api/applications/{applied['id']}", json={"follow_up_date": (date.today() + timedelta(days=4)).isoformat()})

    body = client.get("/api/analytics/funnel").json()
    counts = body["counts"]
    check(counts["tracked"] == 4 and counts["applied"] == 3, counts)
    check(counts["responded"] == 2 and counts["interviews"] == 1 and counts["rejections"] == 1 and counts["offers"] == 0, counts)
    check(body["rates"] is None and str(MIN_APPLIED_FOR_RATES) in body["rates_hidden_reason"], "3 applications are too few for percentages")
    check({c["company"]: c["applied"] for c in body["by_company"]} == {"Acme": 2, "Beta": 1}, body["by_company"])
    check({s["source"] for s in body["by_source"]} == {"lever:acme", "greenhouse:beta"}, body["by_source"])
    follow_ups = {f["application_id"]: f for f in body["upcoming_follow_ups"]}
    check(follow_ups[interview["id"]]["overdue"] is True and follow_ups[applied["id"]]["overdue"] is False, follow_ups)
    check(rejected["id"] not in follow_ups and saved["id"] not in follow_ups, "finished or unscheduled applications are not listed")

    # Enough applications: rates appear and are computed from the real counts.
    more = _make_jobs(8, company="Gamma", source="ashby:gamma")
    for job_id in more:
        client.post("/api/applications", json={"job_id": job_id, "status": "applied"})
    body = client.get("/api/analytics/funnel").json()
    check(body["counts"]["applied"] == 11 and body["rates"] is not None and body["rates_hidden_reason"] is None, body["counts"])
    check(body["rates"]["response_rate"] == round(100 * 2 / 11, 1) and body["rates"]["interview_rate"] == round(100 / 11, 1), body["rates"])


def test_contacts_and_draft_only_outreach() -> None:
    _reset()
    client = TestClient(api_main.app)
    check(client.post("/api/contacts", json={"name": "Priya Sharma", "email": "not-an-email"}).status_code == 422, "bad email refused")
    check(client.post("/api/contacts", json={"name": "Priya", "linkedin_url": "javascript:alert(1)"}).status_code == 422, "non-http link refused")
    check(client.post("/api/contacts", json={"name": "Priya", "follow_up_date": "tomorrow"}).status_code == 422, "bad date refused")

    created = client.post("/api/contacts", json={"name": "Priya Sharma", "kind": "recruiter", "company_name": "Acme", "email": "priya@acme.example"})
    check(created.status_code == 201, created.text)
    contact_id = created.json()["id"]
    referral = client.post("/api/contacts", json={"name": "Ravi Kumar", "kind": "referral", "company_name": "Beta"}).json()
    check([c["name"] for c in client.get("/api/contacts").json()["items"]] == ["Priya Sharma", "Ravi Kumar"], "listed by name")
    check([c["name"] for c in client.get("/api/contacts", params={"kind": "referral"}).json()["items"]] == ["Ravi Kumar"], "filter by kind")
    check([c["name"] for c in client.get("/api/contacts", params={"company": "acme"}).json()["items"]] == ["Priya Sharma"], "filter by company, case-insensitive")
    updated = client.patch(f"/api/contacts/{referral['id']}", json={"referral_status": "asked", "follow_up_date": "2026-12-01"}).json()
    check(updated["referral_status"] == "asked" and updated["follow_up_date"] == "2026-12-01" and updated["name"] == "Ravi Kumar", updated)

    note = client.post(f"/api/contacts/{contact_id}/interactions", json={"kind": "call", "body": "Spoke about the backend role."}).json()
    check(note["status"] == "recorded", note)

    job_id = _make_jobs(1)[0]
    api_main._candidate_profile = lambda: build_candidate_profile()
    draft = client.post(f"/api/contacts/{contact_id}/outreach-draft", json={"job_id": job_id})
    check(draft.status_code == 201, draft.text)
    draft_body = draft.json()
    check(draft_body["sent"] is False and draft_body["status"] == "draft" and "does not send" in draft_body["note"], draft_body)
    check("Priya" in draft_body["body"] and "Backend Engineer" in draft_body["body"] and "Acme" in draft_body["body"], draft_body["body"])
    check(any("name" in w.lower() for w in draft_body["warnings"]), "missing profile name is flagged, not invented")

    # A draft is never "sent" until the user says they sent it themselves; notes cannot be marked sent.
    check(client.post(f"/api/interactions/{note['id']}/mark-sent").status_code == 409, "only drafts can be marked as sent")
    sent = client.post(f"/api/interactions/{draft_body['id']}/mark-sent").json()
    check(sent["status"] == "sent_by_user" and sent["kind"] == "message_sent", sent)
    detail = client.get(f"/api/contacts/{contact_id}").json()
    check({i["kind"] for i in detail["interactions"]} == {"call", "message_sent"}, detail["interactions"])
    check(client.post("/api/interactions/9999/mark-sent").status_code == 404, "unknown interaction")
    check(client.delete(f"/api/contacts/{contact_id}").status_code == 204 and client.get(f"/api/contacts/{contact_id}").status_code == 404, "delete works")

    letter = crm.build_outreach_draft(contact={"name": "Dana"}, facts={"contact_name": "Asha Rao", "current_title": "Systems Engineer", "current_employer": "Example Corp"},
                                      job={"title": "SDE", "company": "Acme"}, verified_skills=["Java", "Python"])
    check("Asha Rao" in letter["body"] and "Java, Python" in letter["body"] and not letter["warnings"], letter)
    check("verified skills" in crm.build_outreach_draft(contact={"name": "Dana"}, facts={}, job=None, verified_skills=[])["warnings"][0], "no skills -> no claim")


def test_referral_workflow_as_the_screen_uses_it() -> None:
    """The Network screen sends nulls for blank fields, changes the referral step from a dropdown, clears the
    follow-up date, and links a contact to a job through a note."""
    _reset()
    client = TestClient(api_main.app)
    job_id = _make_jobs(1)[0]
    created = client.post("/api/contacts", json={
        "name": "Nagendra", "kind": "referral", "role_title": None, "company_name": "Qualcomm", "email": None, "linkedin_url": None,
        "notes": None, "referral_status": "asked", "follow_up_date": "2026-11-25"})
    check(created.status_code == 201 and created.json()["referral_status"] == "asked", created.text)
    contact_id = created.json()["id"]
    check(client.patch(f"/api/contacts/{contact_id}", json={"referral_status": "agreed"}).json()["follow_up_date"] == "2026-11-25",
          "changing the step leaves the date alone")
    cleared = client.patch(f"/api/contacts/{contact_id}", json={"follow_up_date": None}).json()
    check(cleared["follow_up_date"] is None and cleared["referral_status"] == "agreed", cleared)
    check(client.patch(f"/api/contacts/{contact_id}", json={"referral_status": "maybe"}).status_code == 422, "unknown step refused")
    link = client.post(f"/api/contacts/{contact_id}/interactions", json={"kind": "note", "body": "Referral contact for Backend Engineer at Acme.", "job_id": job_id})
    check(link.status_code == 201 and link.json()["job_id"] == job_id, link.text)
    check(client.get(f"/api/contacts/{contact_id}").json()["interactions"][0]["job_id"] == job_id, "the link is kept")


def test_interview_prep_plan() -> None:
    _reset()
    client = TestClient(api_main.app)
    api_main._candidate_profile = lambda: build_candidate_profile()
    job_ids = _make_jobs(2)
    interview_app = client.post("/api/applications", json={"job_id": job_ids[0], "status": "applied"}).json()
    client.patch(f"/api/applications/{interview_app['id']}", json={"status": "interview"})
    assessment_app = client.post("/api/applications", json={"job_id": job_ids[1], "status": "applied"}).json()
    client.patch(f"/api/applications/{assessment_app['id']}", json={"status": "assessment"})

    created = client.post(f"/api/applications/{interview_app['id']}/interview-prep")
    check(created.status_code == 201, created.text)
    plan = created.json()
    categories = plan["categories"]
    check({"technical_questions", "coding_exercises", "system_design", "behavioural", "preparation_steps"} <= set(categories), list(categories))
    check(any("Java" in q["text"] for q in categories["technical_questions"]), "questions follow the job's required skills")
    steps = " ".join(s["text"] for s in categories["preparation_steps"])
    check("Docker" in steps and "Do not claim experience you do not have" in steps, "a skill gap becomes an honest preparation step")
    check("Acme" in steps, "company research step names the company")
    check(plan["progress"] == {"done": 0, "total": sum(len(v) for v in categories.values()), "percent": 0.0}, plan["progress"])

    first_item = categories["coding_exercises"][0]["id"]
    after = client.patch(f"/api/interview-prep/{first_item}", json={"done": True}).json()
    check(after["progress"]["done"] == 1 and after["progress"]["percent"] > 0, after["progress"])
    again = client.post(f"/api/applications/{interview_app['id']}/interview-prep").json()
    check(again["progress"]["total"] == plan["progress"]["total"] and again["progress"]["done"] == 1, "refreshing keeps progress and adds no duplicates")
    check(client.get(f"/api/applications/{interview_app['id']}/interview-prep").json()["progress"]["done"] == 1, "GET returns saved progress")

    early = client.post(f"/api/applications/{assessment_app['id']}/interview-prep").json()
    check("system_design" not in early["categories"] and "coding_exercises" in early["categories"], "the assessment stage focuses on coding, not design rounds")
    check(client.post("/api/applications/9999/interview-prep").status_code == 404, "unknown application")
    check(client.patch("/api/interview-prep/99999", json={"done": True}).status_code == 404, "unknown item")


TESTS = [
    ("Funnel counts, follow-ups and the small-sample rule", test_funnel_counts_and_small_sample_rule),
    ("Contacts and draft-only outreach", test_contacts_and_draft_only_outreach),
    ("Referral workflow as the Network screen uses it", test_referral_workflow_as_the_screen_uses_it),
    ("Interview preparation plan and progress", test_interview_prep_plan),
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
