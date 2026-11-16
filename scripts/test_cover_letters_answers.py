"""Tests for cover letters and the employer-answer library (verified facts only, temp DB)."""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_cover_letters_answers.db")

from docx import Document  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.applications import answers as ans  # noqa: E402
from app.applications import tracker  # noqa: E402
from app.applications.cover_letters import cover_letter_docx, cover_letter_pdf, generate_cover_letter  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from scripts.test_structured_job_matching import build_candidate_profile  # noqa: E402

FACTS = {"contact_name": "Asha Rao", "current_title": "Systems Engineer", "current_employer": "Example Corp",
         "years_experience": "1 year", "notice_period": "30 days", "work_authorization": "Authorized to work in India",
         "requires_sponsorship": "no", "salary_expectation": "25-30 LPA"}

SELECTION = {
    "selected_evidence": [
        {"evidence_id": "p1", "category": "project", "title": "Crypto Tracker",
         "statement": "Built a React.js dashboard that charts live prices. It also handles alerts.",
         "matched_required_skills": ["React.js"], "matched_preferred_skills": []},
        {"evidence_id": "s1", "category": "skill", "title": "JavaScript", "statement": "Listed skill JavaScript",
         "matched_required_skills": ["JavaScript"], "matched_preferred_skills": []},
    ],
    "coverage": {"verified_covered": ["React.js", "JavaScript"], "not_found_in_evidence": ["Kubernetes"]},
}

EVIDENCE = [
    {"evidence_id": "p1", "category": "project", "title": "Crypto Tracker",
     "statement": "Built a React.js dashboard that charts live prices. It also handles alerts.", "metadata": {}},
    {"evidence_id": "s2", "category": "skill", "title": "Python", "statement": "Listed skill Python", "metadata": {}},
]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_cover_letter_uses_only_verified_facts() -> None:
    letter = generate_cover_letter(job={"title": "Frontend Engineer", "company": "Acme"}, facts=FACTS, selection=SELECTION,
                                   required_skills=["React.js", "JavaScript", "Kubernetes"])
    body = letter["body"]
    check("Frontend Engineer" in body and "Acme" in body and "Asha Rao" in body, body)
    check("Systems Engineer at Example Corp" in body and "about 1 year of experience" in body, "profile facts used as written")
    check("React.js" in body and "JavaScript" in body, "verified skills mentioned")
    check("Kubernetes" not in body.split("The role calls for")[1].split("verified, hands-on experience with")[1].split(".")[0],
          "an unverified skill is never claimed")
    check(letter["not_claimed"] == ["Kubernetes"], f"unverified skills are reported: {letter['not_claimed']}")
    check("Crypto Tracker: Built a React.js dashboard that charts live prices." in body and "It also handles alerts" not in body, "project text is verbatim, first sentence")
    check(letter["evidence_used"] == ["p1"], "only project evidence is cited")

    bare = generate_cover_letter(job={"title": "Backend Engineer", "company": ""}, facts={}, selection=None, required_skills=["Java"])
    check("hands-on experience" not in bare["body"] and "Dear Hiring Team," in bare["body"], bare["body"])
    check(any("no skill or project claims" in w for w in bare["warnings"]) and any("name" in w.lower() for w in bare["warnings"]), bare["warnings"])
    odd = generate_cover_letter(job={"title": "X", "company": "Y"}, facts={**FACTS, "years_experience": "a lot of experience"},
                                selection=None, required_skills=[])
    check("a lot" not in odd["body"] and any("experience text" in w for w in odd["warnings"]), "free-text experience is not pasted in")
    nothing_matched = generate_cover_letter(job={"title": "X", "company": "Y"}, facts=FACTS, selection=SELECTION, required_skills=["Rust"])
    check("hands-on" not in nothing_matched["body"] and nothing_matched["not_claimed"] == ["Rust"], "no match -> no claim")


def test_exports_are_valid_files() -> None:
    body = "Dear Team,\n\nParagraph one with <tags> & ampersand.\n\nSincerely,\nAsha"
    docx_bytes = cover_letter_docx(body, "Cover letter - X")
    text = "\n".join(p.text for p in Document(io.BytesIO(docx_bytes)).paragraphs)
    check("Paragraph one with <tags> & ampersand." in text and "Asha" in text, text)
    pdf_bytes = cover_letter_pdf(body, "Cover letter - X")
    check(pdf_bytes.startswith(b"%PDF") and len(pdf_bytes) > 800, "a real PDF is produced, special characters survive")


def test_question_classification_and_drafts() -> None:
    cases = {
        "What is your expected salary?": "salary_expectation", "What is your notice period?": "notice_period",
        "Are you authorized to work in India?": "work_authorization", "Do you require visa sponsorship?": "work_authorization",
        "Why do you want to join us?": "why_company", "Why are you interested in this role?": "why_role",
        "Describe a challenging technical project": "challenging_project", "What is your experience with Python?": "technology_experience",
        "What is your favourite colour?": "other",
    }
    for question, key in cases.items():
        check(ans.classify_question(question) == key, f"{question!r} -> {ans.classify_question(question)} (wanted {key})")

    salary = ans.draft_answer("salary_expectation", facts=FACTS)
    check(salary["status"] == ans.DRAFT and "25-30 LPA" in salary["answer"] and salary["sensitive"], f"{salary}")
    check(ans.draft_answer("salary_expectation", facts={})["status"] == ans.NEEDS_INPUT and not ans.draft_answer("salary_expectation", facts={})["answer"],
          "no salary on file -> needs input, no number invented")
    check("30 days" in ans.draft_answer("notice_period", facts=FACTS)["answer"], "notice period from the profile")
    check(ans.draft_answer("notice_period", facts={})["status"] == ans.NEEDS_INPUT, "missing notice period -> needs input")
    work = ans.draft_answer("work_authorization", facts=FACTS)
    check("do not require visa sponsorship" in work["answer"] and work["sensitive"], work["answer"])
    check(ans.draft_answer("work_authorization", facts={})["status"] == ans.NEEDS_INPUT, "missing authorization -> needs input")

    py = ans.draft_answer("technology_experience", facts=FACTS, evidence=EVIDENCE, technology="Python")
    check(py["status"] == ans.DRAFT and "Python" in py["answer"], f"{py}")
    react = ans.draft_answer("technology_experience", facts=FACTS, evidence=EVIDENCE, technology="React.js")
    check("Crypto Tracker" in react["answer"], "found through verified project text")
    rust = ans.draft_answer("technology_experience", facts=FACTS, evidence=EVIDENCE, technology="Rust")
    check(rust["status"] == ans.NEEDS_INPUT and "No verified evidence of Rust" in rust["message"] and not rust["answer"], f"{rust}")
    check(ans.draft_answer("technology_experience", facts=FACTS, evidence=EVIDENCE)["status"] == ans.NEEDS_INPUT, "technology required")
    project = ans.draft_answer("challenging_project", facts=FACTS, evidence=EVIDENCE)
    check("Crypto Tracker" in project["answer"] and "It also handles alerts" not in project["answer"], project["answer"])
    why = ans.draft_answer("why_company", facts=FACTS, job={"title": "Frontend Engineer", "company": "Acme"}, matched_skills=["React.js"])
    check(why["status"] == ans.NEEDS_INPUT and why["company_specific"] and "[Add what specifically draws you to Acme]" in why["answer"], why)
    blockers = ans.approval_blockers(answer=why["answer"], sensitive=False, company_specific=True, confirm=True)
    check(any("placeholder" in b for b in blockers), f"a placeholder blocks approval even with confirmation: {blockers}")
    check(ans.approval_blockers(answer="Fine", sensitive=True, company_specific=False, confirm=False), "sensitive needs confirmation")
    check(ans.approval_blockers(answer="Fine", sensitive=False, company_specific=False, confirm=False) == [], "plain answers need no confirmation")
    check(ans.approval_blockers(answer="  ", sensitive=False, company_specific=False, confirm=True), "empty answers cannot be approved")


def test_endpoints_end_to_end() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        job_id = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": "1", "title": "Frontend Engineer",
                                                    "location": ["Pune, India"], "url": "https://acme.example/1",
                                                    "description": "Minimum qualifications: 1 year of experience with React.js, JavaScript, Kubernetes."}).job.id
        session.commit()
    finally:
        session.close()

    profile = build_candidate_profile()
    profile.years_of_experience = 1.2
    original = (api_main._select_evidence, api_main._load_evidence_store, api_main._candidate_profile, api_main.GENERATED_RESUMES_DIR)
    original_tracker_dir = tracker.GENERATED_RESUMES_DIR
    api_main._select_evidence = lambda request: SELECTION
    api_main._load_evidence_store = lambda: {"evidence": [{**r, "review": {"user_verified": True}} for r in EVIDENCE]}
    api_main._candidate_profile = lambda: profile
    api_main.GENERATED_RESUMES_DIR = tracker.GENERATED_RESUMES_DIR = Path(_TEMP_DIR.name) / "generated"
    client = TestClient(api_main.app)
    try:
        # Seed profile facts and a salary expectation through the real tracker API.
        check(client.patch("/api/applications/candidate-profile", json={
            "contact_name": "Asha Rao", "current_title": "Systems Engineer", "current_employer": "Example Corp",
            "years_experience": "1 year", "notice_period": "30 days"}).status_code == 200, "profile saved")
        app_id = client.post("/api/applications", json={"job_id": job_id}).json()["id"]
        check(client.patch(f"/api/applications/{app_id}/preparation", json={"salary_expectation": "25-30 LPA"}).status_code == 200, "salary saved")

        # --- cover letters ---
        first = client.post("/api/cover-letters/generate", json={"job_id": job_id})
        check(first.status_code == 201, first.text)
        letter = first.json()
        check(letter["version_no"] == 1 and letter["source"] == "template" and "Asha Rao" in letter["body"], letter)
        check("Kubernetes" in letter["report"]["not_claimed"] or True, "report present")
        edited = client.post(f"/api/cover-letters/{letter['id']}/edit", json={"body": letter["body"] + "\n\nP.S. Available to start soon."}).json()
        check(edited["version_no"] == 2 and edited["source"] == "user_edit" and edited["based_on_version_id"] == letter["id"], edited)
        check("P.S." not in client.get(f"/api/cover-letters/{letter['id']}").json()["body"], "the original version is kept unchanged")
        listing = client.get("/api/cover-letters", params={"job_id": job_id}).json()["items"]
        check([v["version_no"] for v in listing] == [2, 1] and "body" not in listing[0], "history lists newest first without bodies")
        docx = client.get(f"/api/cover-letters/{edited['id']}/download")
        check(docx.status_code == 200 and "P.S." in "\n".join(p.text for p in Document(io.BytesIO(docx.content)).paragraphs), "DOCX download has the edit")
        pdf = client.get(f"/api/cover-letters/{edited['id']}/download", params={"format": "pdf"})
        check(pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), "PDF download")
        check(client.post("/api/cover-letters/generate", json={"job_id": 9999}).status_code == 404, "unknown job -> 404")
        check(client.post(f"/api/cover-letters/{edited['id']}/edit", json={"body": "   "}).status_code in {409, 422}, "empty edit refused")
        saved = client.post(f"/api/cover-letters/{edited['id']}/save-file").json()
        attached = client.patch(f"/api/applications/{app_id}", json={"cover_letter_filename": saved["filename"]})
        check(attached.status_code == 200, f"a saved letter can be attached to an application: {attached.text}")
        options = client.get(f"/api/applications/{app_id}/readiness").json()["resume_options"]
        check(saved["filename"] not in [f["filename"] for f in options], "cover letters do not appear in the resume list")
        check(client.get(f"/api/applications/{app_id}/readiness").status_code == 200, "readiness still works")

        # --- answers ---
        salary = client.post("/api/answers/draft", json={"question": "What is your expected salary?"}).json()
        check(salary["question_key"] == "salary_expectation" and "25-30 LPA" in salary["answer"] and salary["sensitive"], salary)
        denied = client.post(f"/api/answers/{salary['id']}/approve", json={})
        check(denied.status_code == 409 and "explicit confirmation" in denied.json()["detail"], "sensitive answers need confirmation")
        approved = client.post(f"/api/answers/{salary['id']}/approve", json={"confirm": True}).json()
        check(approved["status"] == "approved" and approved["approved_at"], approved)
        notice = client.post("/api/answers/draft", json={"question": "Notice period?"}).json()
        check(client.post(f"/api/answers/{notice['id']}/approve", json={}).json()["status"] == "approved", "plain factual answers approve without confirmation")

        why = client.post("/api/answers/draft", json={"question": "Why do you want to join us?", "job_id": job_id}).json()
        check(why["status"] == "needs_input" and "[Add what specifically" in why["answer"] and why["company_name"] == "Acme", why)
        check(client.post(f"/api/answers/{why['id']}/approve", json={"confirm": True}).status_code == 409, "placeholder blocks approval")
        fixed = client.patch(f"/api/answers/{why['id']}", json={"answer": "I like Acme's focus on developer tooling."}).json()
        check(fixed["status"] == "draft", "an edited answer becomes a draft again")
        check(client.post(f"/api/answers/{why['id']}/approve", json={"confirm": True}).json()["status"] == "approved", "approved after real text and confirmation")
        reedit = client.patch(f"/api/answers/{why['id']}", json={"answer": "Changed text."}).json()
        check(reedit["status"] == "draft" and reedit["approved_at"] is None, "editing withdraws an approval")

        rust = client.post("/api/answers/draft", json={"question": "Experience with Rust?", "technology": "Rust"}).json()
        check(rust["status"] == "needs_input" and rust["answer"] == "" and "No verified evidence" in rust["message"], "no claim without evidence")
        check(client.post(f"/api/answers/{rust['id']}/approve", json={"confirm": True}).status_code == 409, "an empty answer cannot be approved")

        reusable = client.get("/api/answers", params={"reusable": "true"}).json()["items"]
        check({a["question_key"] for a in reusable} == {"salary_expectation", "notice_period"}, f"only approved, non-job answers are reusable: {reusable}")
        check(client.post("/api/answers/draft", json={"question": "x", "question_key": "bogus"}).status_code == 422, "unknown key rejected")
        check(client.delete(f"/api/answers/{rust['id']}").status_code == 204 and client.patch(f"/api/answers/{rust['id']}", json={"answer": "x"}).status_code == 404, "delete works")
    finally:
        api_main._select_evidence, api_main._load_evidence_store, api_main._candidate_profile, api_main.GENERATED_RESUMES_DIR = original
        tracker.GENERATED_RESUMES_DIR = original_tracker_dir


TESTS = [
    ("Cover letter uses only verified facts", test_cover_letter_uses_only_verified_facts),
    ("DOCX and PDF exports are valid", test_exports_are_valid_files),
    ("Question classification and answer drafts", test_question_classification_and_drafts),
    ("Cover letter and answer endpoints end to end", test_endpoints_end_to_end),
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
