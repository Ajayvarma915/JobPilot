"""Tests for the tailoring report, the no-fabrication check and resume version storage.

Synthetic evidence only; temporary database and output folder. Never reads your master resume.
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["JOBPILOT_DATABASE_PATH"] = str(Path(_TEMP_DIR.name) / "test_resume_versions.db")

from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import main as api_main  # noqa: E402
from app.db.database import Base, SessionLocal, engine  # noqa: E402
from app.db.job_repository import JobRepository  # noqa: E402
from app.resume.resume_builder import build_tailored_resume  # noqa: E402
from app.resume.tailoring_report import build_tailoring_report, fabrication_check  # noqa: E402
from scripts.test_resume_builder import _fixture  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _selection_and_store():
    selection, store = _fixture()
    selection = copy.deepcopy(selection)
    for item in selection["selected_evidence"]:
        if item["category"] == "skill" and item["title"] == "React.js":
            item["matched_required_skills"] = ["React.js"]
    selection["coverage"] = {
        "required_skills": 3,
        "verified_covered": ["React.js"],
        "awaiting_evidence_review": ["TypeScript"],
        "not_found_in_evidence": ["Kubernetes"],
    }
    selection["review_queue"] = [{"evidence_id": "unverified-1", "title": "Unverified project",
                                  "matched_required_skills": ["TypeScript"]}]
    return selection, store


def test_report_contents() -> None:
    selection, store = _selection_and_store()
    report = build_tailoring_report(selection, store)
    check(report["job_title"] == "Frontend Software Engineer", "job title")
    check(any(e["category"] == "education" and "core section" in e["why_selected"][0] for e in report["evidence_reused"]),
          "verified education is listed as a core section")
    check("React.js" in report["keywords_aligned"], f"keywords: {report['keywords_aligned']}")
    check(report["required_skills"]["no_evidence_found"] == ["Kubernetes"]
          and report["required_skills"]["awaiting_your_review"] == ["TypeScript"], f"{report['required_skills']}")
    kinds = {n["kind"] for n in report["needs_review"]}
    check(kinds == {"unverified_evidence", "uncovered_required_skill"}, f"needs review: {kinds}")
    check(any("Do not claim it unless it is true" in n["why"] for n in report["needs_review"]), "uncovered skills carry a no-claim warning")
    check(report["wording"] == {"bullets_rewritten": False, "claims_generated": False}, "wording flags")
    check(report["original_resume"]["modified"] is False, "original untouched")
    check(all("copied unchanged" in s["change"] for s in report["sections_changed"]), "sections explain that text is copied")


def test_fabrication_check_catches_invented_bullets() -> None:
    selection, store = _selection_and_store()
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "resume.docx"
        build_tailored_resume(selection, store, output)
        clean = fabrication_check(output, store, selection)
        check(clean["ok"] and clean["bullets_checked"] > 0, f"a faithful resume passes: {clean}")

        tampered = Document(str(output))
        tampered.add_paragraph("Led a team of 50 engineers and cut costs by 90%", style="List Bullet")
        tampered_path = Path(directory) / "tampered.docx"
        tampered.save(str(tampered_path))
        result = fabrication_check(tampered_path, store, selection)
        check(not result["ok"] and "Led a team of 50 engineers and cut costs by 90%" in result["violations"], f"{result}")

        # Text of an UNVERIFIED record is not allowed either.
        unverified_store = copy.deepcopy(store)
        unverified_store["evidence"].append({
            "evidence_id": "u1", "category": "project", "title": "Secret project", "statement": "Built a rocket",
            "source": {"file": "x", "section": "projects", "text": "Built a rocket"}, "metadata": {},
            "review": {"status": "needs_review", "user_verified": False},
        })
        sneaky = Document(str(output))
        sneaky.add_paragraph("Built a rocket", style="List Bullet")
        sneaky_path = Path(directory) / "sneaky.docx"
        sneaky.save(str(sneaky_path))
        check(not fabrication_check(sneaky_path, unverified_store, selection)["ok"], "unverified evidence text is rejected")


def _setup_job():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        repo = JobRepository(session)
        company = repo.get_or_create_company("Acme")
        job = repo.upsert_job_detailed(company, {"source": "lever:acme", "external_id": "1", "title": "Frontend Software Engineer",
                                                 "location": ["Pune, India"], "url": "https://acme.example/1",
                                                 "description": "Minimum qualifications: 1 year of experience with React.js."}).job
        session.commit()
        return job.id
    finally:
        session.close()


def test_generate_persists_versions_and_fails_closed() -> None:
    job_id = _setup_job()
    selection, store = _selection_and_store()
    out_dir = Path(_TEMP_DIR.name) / "generated"
    original = (api_main._select_evidence, api_main._load_evidence_store, api_main.GENERATED_RESUMES_DIR, api_main.build_tailored_resume)
    api_main._select_evidence = lambda request: selection
    api_main._load_evidence_store = lambda: store
    api_main.GENERATED_RESUMES_DIR = out_dir
    client = TestClient(api_main.app)
    payload = {"job_title": "Frontend Software Engineer", "job_description": "We need React.js and TypeScript experience " * 2, "job_id": job_id}
    try:
        first = client.post("/api/resumes/generate", json=payload)
        check(first.status_code == 201, first.text)
        body = first.json()
        check(body["version_id"] and body["fabrication_check"]["ok"] and body["report"]["wording"]["bullets_rewritten"] is False, f"{body.keys()}")

        second = client.post("/api/resumes/generate", json=payload).json()
        # Back-to-back generations (usually inside one second) must never share a filename,
        # otherwise cleaning up a refused one could delete a good version's files.
        check(body["resume_filename"] != second["resume_filename"] and body["pdf_filename"] != second["pdf_filename"],
              "two generations in the same second need different filenames")
        check((out_dir / body["resume_filename"]).is_file() and (out_dir / second["resume_filename"]).is_file(), "both versions keep their files")
        listing = client.get("/api/resume-versions").json()
        check([v["id"] for v in listing["items"]] == [second["version_id"], body["version_id"]], "newest version first")
        item = listing["items"][0]
        check(item["company_name"] == "Acme" and item["job_id"] == job_id and item["files_present"] == {"docx": True, "pdf": True}, f"{item}")
        check(client.get("/api/resume-versions", params={"job_id": job_id + 99}).json()["items"] == [], "filter by job")
        detail = client.get(f"/api/resume-versions/{body['version_id']}").json()
        check(detail["report"]["keywords_aligned"] and detail["fabrication_check"]["ok"] and "ats_readability" in detail["evaluation"], "detail has report and checks")
        check(client.get(item["download_url"]).status_code == 200 and client.get(item["pdf_download_url"]).status_code == 200, "both files download")
        check(client.get("/api/resume-versions/9999").status_code == 404, "unknown version -> 404")

        files_before = sorted(p.name for p in out_dir.iterdir())
        check(client.post("/api/resumes/generate", json={**payload, "job_id": 9999}).status_code == 404, "unknown job -> 404")
        check(sorted(p.name for p in out_dir.iterdir()) == files_before, "nothing is generated for an unknown job")

        def tampering_builder(selection_arg, store_arg, output_path, audit_path=None):
            build_tailored_resume(selection_arg, store_arg, output_path, audit_path=audit_path)
            document = Document(str(output_path))
            document.add_paragraph("Invented achievement: doubled revenue", style="List Bullet")
            document.save(str(output_path))
            return output_path

        api_main.build_tailored_resume = tampering_builder
        refused = client.post("/api/resumes/generate", json=payload)
        check(refused.status_code == 422 and "not backed by your verified evidence" in refused.json()["detail"], refused.text)
        check(sorted(p.name for p in out_dir.iterdir()) == files_before, "a refused resume leaves no files behind")
        check(len(client.get("/api/resume-versions").json()["items"]) == 2, "a refused resume is not stored as a version")
    finally:
        api_main._select_evidence, api_main._load_evidence_store, api_main.GENERATED_RESUMES_DIR, api_main.build_tailored_resume = original


TESTS = [
    ("Tailoring report explains what was reused and what needs review", test_report_contents),
    ("No-fabrication check rejects invented and unverified text", test_fabrication_check_catches_invented_bullets),
    ("Versions are stored per job and a fabricated resume is refused", test_generate_persists_versions_and_fails_closed),
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
