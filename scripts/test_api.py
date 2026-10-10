from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.main as api_module
from app.db.models import Base, Company, Job


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _evidence_record(
    *,
    evidence_id: str,
    category: str,
    title: str,
    statement: str,
    section: str,
    source_text: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "category": category,
        "title": title,
        "statement": statement,
        "source": {
            "file": "test_resume.pdf",
            "section": section,
            "text": source_text,
        },
        "metadata": metadata or {},
        "review": {
            "status": "verified",
            "user_verified": True,
            "reviewed_at_utc": "2026-10-10T00:00:00Z",
            "note": "Verified in the API test fixture.",
        },
    }


def _write_test_evidence_store(path: Path) -> None:
    evidence = [
        _evidence_record(
            evidence_id="skill-javascript",
            category="skill",
            title="JavaScript",
            statement="Listed as a skill: JavaScript.",
            section="skills",
            source_text="JavaScript",
            metadata={"skill_group": "programming_language"},
        ),
        _evidence_record(
            evidence_id="project-dashboard",
            category="project",
            title="Dashboard Demo",
            statement=(
                "Built a frontend dashboard using JavaScript and React.js."
            ),
            section="projects",
            source_text=(
                "Dashboard Demo\n"
                "Built a frontend dashboard using JavaScript and React.js."
            ),
            metadata={
                "technologies": ["JavaScript", "React.js"],
                "bullets": [
                    (
                        "Built a frontend dashboard using JavaScript "
                        "and React.js."
                    )
                ],
            },
        ),
        _evidence_record(
            evidence_id="education-bachelor",
            category="education",
            title="Bachelor — Computer Science — Example University",
            statement=(
                "Bachelor in Computer Science at Example University; CGPA 8.8."
            ),
            section="education",
            source_text=(
                "BTech - Computer Science\n"
                "Example University\n"
                "CGPA: 8.8"
            ),
            metadata={
                "degree": "Bachelor",
                "field_of_study": "Computer Science",
                "institution": "Example University",
                "cgpa": 8.8,
                "start_date": "2021",
                "end_date": "2025",
                "location": "Hyderabad, Telangana",
            },
        ),
    ]

    data = {
        "schema_version": 1,
        "created_at_utc": "2026-10-10T00:00:00Z",
        "source_resume": {
            "file": "test_resume.pdf",
            "absolute_path": "test_resume.pdf",
            "format": ".pdf",
            "sha256": "test-fingerprint",
        },
        "candidate": {
            "name": "TEST CANDIDATE",
            "email": "test@example.com",
            "phone": "+91-9000000000",
            "linkedin": "linkedin.com/in/test",
            "github": "github.com/test",
            "location": "Hyderabad, Telangana",
        },
        "evidence_count": len(evidence),
        "counts_by_category": {
            "education": 1,
            "project": 1,
            "skill": 1,
        },
        "evidence": evidence,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _seed_test_database(session_factory) -> None:
    with session_factory() as db:
        company = Company(
            name="Acme Systems",
            website="https://example.invalid",
            careers_url="https://example.invalid/careers",
            source_type="test",
        )

        db.add(company)
        db.flush()

        job = Job(
            company_id=company.id,
            external_id="api-test-001",
            title="Frontend Software Engineer",
            location="Hyderabad, Telangana, India",
            url="https://example.invalid/jobs/frontend-engineer",
            description=(
                "Build frontend applications with Python, JavaScript, "
                "React.js, HTML, and CSS."
            ),
            source="api_test",
            experience_level="entry",
            employment_type="full-time",
            is_active=True,
        )

        db.add(job)
        db.commit()


def test_health_stats_jobs(client: TestClient) -> None:
    root_response = client.get("/")
    check(root_response.status_code == 200, "Root endpoint failed.")
    check(
        root_response.json()["application"] == "JobPilot",
        "Root endpoint application name is wrong.",
    )

    health_response = client.get("/api/health")
    check(
        health_response.status_code == 200,
        f"Health endpoint failed: {health_response.text}",
    )

    health = health_response.json()
    check(health["status"] == "ok", "API health status is wrong.")
    check(
        health["database"] == "connected",
        "API database dependency did not connect.",
    )
    check(
        health["jobs_available"] == 1,
        f"Unexpected job count in health endpoint: {health}",
    )

    stats_response = client.get("/api/dashboard/stats")
    check(
        stats_response.status_code == 200,
        "Dashboard stats endpoint failed.",
    )

    stats = stats_response.json()
    check(stats["total_jobs"] == 1, "Total jobs count is wrong.")
    check(stats["active_jobs"] == 1, "Active jobs count is wrong.")
    check(stats["total_companies"] == 1, "Company count is wrong.")

    list_response = client.get("/api/jobs?limit=10&offset=0")
    check(
        list_response.status_code == 200,
        f"Jobs endpoint failed: {list_response.text}",
    )

    listing = list_response.json()
    check(len(listing["items"]) == 1, "Expected one test job.")
    check(
        listing["items"][0]["title"] == "Frontend Software Engineer",
        "Job title was serialized incorrectly.",
    )
    check(
        listing["items"][0]["company"]["name"] == "Acme Systems",
        "Company name was serialized incorrectly.",
    )
    check(listing["pagination"]["total"] == 1, "Pagination total is wrong.")

    search_response = client.get("/api/jobs?q=Python")
    check(search_response.status_code == 200, "Job search failed.")
    check(
        len(search_response.json()["items"]) == 1,
        "Search did not find the Python job.",
    )

    company_response = client.get("/api/jobs?company=Acme")
    check(company_response.status_code == 200, "Company filter failed.")
    check(
        len(company_response.json()["items"]) == 1,
        "Company filter did not return the expected job.",
    )

    detail_response = client.get("/api/jobs/1")
    check(
        detail_response.status_code == 200,
        "Job detail endpoint failed.",
    )
    check(
        detail_response.json()["id"] == 1,
        "Job detail ID is wrong.",
    )

    missing_response = client.get("/api/jobs/9999")
    check(
        missing_response.status_code == 404,
        "Missing job should return HTTP 404.",
    )


def test_evidence_summary_and_selection(client: TestClient) -> None:
    summary_response = client.get("/api/evidence/summary")
    check(
        summary_response.status_code == 200,
        "Evidence summary endpoint failed.",
    )

    summary = summary_response.json()
    check(summary["status"] == "ready", "Evidence store is not ready.")
    check(summary["record_count"] == 3, "Evidence count is wrong.")
    check(summary["verified_count"] == 3, "Verified count is wrong.")
    check(summary["pending_count"] == 0, "Pending count is wrong.")

    request_data = {
        "job_title": "Frontend Software Engineer",
        "job_description": (
            "Build web interfaces using JavaScript and React.js. "
            "Create responsive frontend components."
        ),
        "required_skills": ["JavaScript"],
        "preferred_skills": ["React.js"],
        "max_projects": 3,
    }

    response = client.post(
        "/api/evidence/select",
        json=request_data,
    )

    check(
        response.status_code == 200,
        f"Evidence selection failed: {response.text}",
    )

    selection = response.json()
    check(
        selection["coverage"]["verified_covered"] == ["JavaScript"],
        f"Required-skill coverage is wrong: {selection['coverage']}",
    )
    check(
        selection["selected_evidence"],
        "Verified evidence was not selected.",
    )
    check(
        all(
            item["user_verified"] is True
            for item in selection["selected_evidence"]
        ),
        "Selector returned an unverified item as selected evidence.",
    )


def test_resume_generation_and_download(client: TestClient, output_dir: Path) -> None:
    request_data = {
        "job_title": "Frontend Software Engineer",
        "job_description": (
            "Build web interfaces using JavaScript and React.js. "
            "Create responsive frontend components."
        ),
        "required_skills": ["JavaScript"],
        "preferred_skills": ["React.js"],
        "max_projects": 3,
    }

    response = client.post(
        "/api/resumes/generate",
        json=request_data,
    )

    check(
        response.status_code == 201,
        f"Resume generation failed: {response.text}",
    )

    result = response.json()
    check(
        result["status"] == "created",
        f"Unexpected generation result: {result}",
    )
    check(
        result["selected_evidence_count"] > 0,
        "Resume generation used no selected evidence.",
    )
    check(
        result["safety"]["claims_invented"] is False,
        "Resume generation safety flag is wrong.",
    )

    filename = result["resume_filename"]
    resume_path = output_dir / filename
    audit_path = resume_path.with_suffix(".audit.json")

    check(resume_path.is_file(), "DOCX file was not created.")
    check(resume_path.stat().st_size > 1000, "Generated DOCX is too small.")
    check(audit_path.is_file(), "Audit file was not created.")

    download_response = client.get(result["download_url"])
    check(
        download_response.status_code == 200,
        "Resume download endpoint failed.",
    )
    check(
        len(download_response.content) > 1000,
        "Downloaded DOCX is unexpectedly small.",
    )


def main() -> int:
    print("=" * 68)
    print("JobPilot FastAPI Tests")
    print("=" * 68)

    original_store_path = api_module.EVIDENCE_STORE_PATH
    original_output_dir = api_module.GENERATED_RESUMES_DIR

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    test_session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    passed = 0
    failed = 0

    with tempfile.TemporaryDirectory() as temp_dir:
        temporary_root = Path(temp_dir)
        evidence_path = temporary_root / "master_resume_evidence.json"
        output_dir = temporary_root / "generated_resumes"

        try:
            Base.metadata.create_all(bind=test_engine)
            _seed_test_database(test_session_factory)
            _write_test_evidence_store(evidence_path)

            api_module.EVIDENCE_STORE_PATH = evidence_path
            api_module.GENERATED_RESUMES_DIR = output_dir

            def override_get_db():
                db = test_session_factory()
                try:
                    yield db
                finally:
                    db.close()

            api_module.app.dependency_overrides[
                api_module.get_db
            ] = override_get_db

            tests = [
                (
                    "Health, dashboard stats, search, filters, and job details",
                    lambda client: test_health_stats_jobs(client),
                ),
                (
                    "Evidence summary and verified evidence selection",
                    lambda client: test_evidence_summary_and_selection(client),
                ),
                (
                    "Resume generation and document download",
                    lambda client: test_resume_generation_and_download(
                        client,
                        output_dir,
                    ),
                ),
            ]

            with TestClient(api_module.app) as client:
                for number, (name, test) in enumerate(tests, start=1):
                    try:
                        test(client)
                        passed += 1
                        print(f"Test {number}: PASS - {name}")
                    except Exception as exc:
                        failed += 1
                        print(
                            f"Test {number}: FAIL - {name}\n"
                            f"  {type(exc).__name__}: {exc}"
                        )

        finally:
            api_module.app.dependency_overrides.clear()
            api_module.EVIDENCE_STORE_PATH = original_store_path
            api_module.GENERATED_RESUMES_DIR = original_output_dir
            test_engine.dispose()

    print(f"\nUnit tests: {passed} passed, {failed} failed")

    if failed:
        print("FAILURE: JobPilot API tests failed.")
        return 1

    print("SUCCESS: JobPilot API tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())