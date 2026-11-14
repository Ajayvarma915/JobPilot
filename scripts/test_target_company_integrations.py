from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.collectors.ashby import AshbyCollector
from app.collectors.amazon_jobs import AmazonJobsCollector
from app.collectors.company_ats_discovery import detect_ats_links, integration_config_from_source
from app.collectors.smartrecruiters import SmartRecruitersCollector
from app.collectors.workday import WorkdayCollector
from app.collectors.oracle_hcm import OracleHCMCollector
from app.services.target_role_policy import (
    extract_minimum_experience_years,
    is_target_software_role,
    is_india_or_remote_eligible,
)

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return self.payload


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_registry_has_all_30_unique_target_companies() -> None:
    payload = json.loads((ROOT / "data" / "target_companies.json").read_text(encoding="utf-8"))
    companies = payload["companies"]
    check(len(companies) == 30, f"Expected 30 targets, got {len(companies)}")
    ids = [item["id"] for item in companies]
    names = [item["name"] for item in companies]
    check(len(ids) == len(set(ids)), "Company IDs must be unique")
    check(len(names) == len(set(names)), "Company names must be unique")
    check(payload["candidate"]["experience_start_date"] == "2025-09-18", "Candidate joining date mismatch")
    check(payload["candidate"]["compensation_disclosure_required"] is False, "Salary disclosure must not gate job discovery")
    active = {item["id"] for item in companies if item.get("integration", {}).get("status") == "active"}
    configured = {item["id"] for item in companies if item.get("integration", {}).get("status") == "configured_needs_live_validation"}
    check({"google", "nvidia", "cred", "meesho"}.issubset(active), "Expected verified Google/NVIDIA/CRED/Meesho sources")
    # Updated 14 Nov after live read-only dry runs (see the `notes` of each entry in
    # target_companies.json): Amazon, Razorpay, Groww and BrowserStack were validated
    # and promoted; Uber (ownership of the Oracle site unconfirmed), Adobe (Workday wd5
    # outage) and Freshworks (no descriptions yet) stay awaiting validation.
    check({"amazon", "razorpay", "groww", "browserstack"}.issubset(active), "Amazon/Razorpay/Groww/BrowserStack were validated live on 2026-11-14")
    check({"uber", "adobe", "freshworks"} == configured, f"Uber/Adobe/Freshworks should remain awaiting validation, got {sorted(configured)}")
    for item in companies:
        integration = item.get("integration", {})
        if integration.get("status") == "active":
            check(integration.get("verified") is True and bool(integration.get("validated_at") or item["id"] in {"google", "nvidia", "cred", "meesho"}),
                  f"{item['id']} is active without verification evidence")


def test_ashby_public_job_board_normalization_and_deduplication() -> None:
    collector = AshbyCollector("sample", "Sample Co")
    payload = {
        "apiVersion": "1",
        "jobs": [
            {
                "jobId": "ashby-1",
                "title": "Software Engineer I",
                "location": "Bengaluru, India",
                "secondaryLocations": [{"location": "Hyderabad, India"}],
                "department": "Engineering",
                "team": "Platform",
                "isRemote": False,
                "employmentType": "Full time",
                "jobUrl": "https://jobs.ashbyhq.com/sample/ashby-1",
                "descriptionPlain": "Build backend systems.",
                "publishedAt": "2026-11-01T10:00:00.000Z",
                "isListed": True,
            },
            {
                "jobId": "ashby-1",
                "title": "Duplicate",
                "location": "India",
                "jobUrl": "https://jobs.ashbyhq.com/sample/ashby-1",
                "isListed": True,
            },
            {
                "jobId": "unlisted-1",
                "title": "Unlisted role",
                "location": "India",
                "jobUrl": "https://jobs.ashbyhq.com/sample/unlisted-1",
                "isListed": False,
            },
        ],
    }
    with patch.object(collector.session, "get", return_value=FakeResponse(payload)):
        jobs = collector.collect()
    check(len(jobs) == 1, "Ashby duplicate/unlisted jobs should be excluded")
    job = jobs[0]
    check(job["source"] == "ashby:sample", "Ashby source identifier missing")
    check(job["location"] == ["Bengaluru, India", "Hyderabad, India"], "Ashby locations missing")
    check(job["description"] == "Build backend systems.", "Ashby description missing")


def test_smartrecruiters_pagination_and_normalization() -> None:
    collector = SmartRecruitersCollector("sample", "Sample Co", page_size=1, max_pages=3)
    first = {"content": [{
        "id": "sr-1", "name": "Backend Engineer", "ref": "https://jobs.smartrecruiters.com/sample/sr-1",
        "location": {"city": "Bengaluru", "region": "Karnataka", "country": "India"},
        "typeOfEmployment": {"label": "Full-time"}, "department": {"label": "Engineering"},
    }], "totalFound": 2}
    second = {"content": [{
        "id": "sr-2", "name": "Software Engineer", "ref": "https://jobs.smartrecruiters.com/sample/sr-2",
        "location": {"fullLocation": "Hyderabad, India"},
    }], "totalFound": 2}
    with patch.object(collector.session, "get", side_effect=[FakeResponse(first), FakeResponse(second)]):
        jobs = collector.collect()
    check(len(jobs) == 2, "SmartRecruiters should fetch both pages")
    check(jobs[0]["source"] == "smartrecruiters:sample", "SmartRecruiters source missing")
    check(jobs[0]["location"] == ["Bengaluru, Karnataka, India"], "SmartRecruiters location missing")
    check(jobs[0]["employment_type"] == "Full-time", "SmartRecruiters employment type missing")


def test_workday_search_and_detail_normalization() -> None:
    collector = WorkdayCollector(
        tenant="nvidia", site="NVIDIAExternalCareerSite", company_name="NVIDIA",
        host="https://nvidia.wd5.myworkdayjobs.com", fetch_details=True, page_size=20,
    )
    summary = {"total": 1, "jobPostings": [{
        "title": "Software Engineer I",
        "externalPath": "/job/India-Hyderabad/Software-Engineer-I_JR123",
        "jobReqId": "JR123", "locationsText": "India, Hyderabad", "postedOn": "Nov 01, 2026",
        "jobFamilyGroup": "Engineering",
    }]}
    detail = {"jobPostingInfo": {
        "jobTitle": "Software Engineer I", "jobDescription": "<p>Build distributed services.</p>",
        "timeType": "Full time", "postedOn": "Nov 01, 2026",
    }}
    with patch.object(collector.session, "post", return_value=FakeResponse(summary)) as post_mock:
        with patch.object(collector.session, "get", return_value=FakeResponse(detail)) as get_mock:
            jobs = collector.collect()
    check(len(jobs) == 1, "Workday job should be collected")
    check(post_mock.call_args.kwargs["json"]["searchText"] == "", "Workday search should request the complete public board")
    check(get_mock.called, "Workday detail endpoint should be called")
    job = jobs[0]
    check(job["external_id"] == "JR123", "Workday requisition ID missing")
    check(job["source"] == "workday:nvidia:nvidiaexternalcareersite", "Workday source missing")
    check("Build distributed services." in job["description"], "Workday detail description missing")



def test_amazon_public_search_normalization_and_experience_bands() -> None:
    collector = AmazonJobsCollector(max_pages_per_band=1, page_size=2, fetch_details=False)
    payload = {"jobs": [
        {"id": "123", "title": "Software Development Engineer I", "job_path": "/en/jobs/123/software-development-engineer-i", "location": "Hyderabad, India", "description": "Basic qualifications: 1+ years of professional experience."},
        {"id": "124", "title": "Backend Software Engineer", "job_path": "/en/jobs/124/backend", "location": "Bengaluru, India", "description": "Build backend systems."},
    ]}
    with patch.object(collector.session, "get", return_value=FakeResponse(payload)) as get_mock:
        jobs = collector.collect()
    check(len(jobs) == 2, "Amazon collector should deduplicate the same role found in both experience bands")
    check(jobs[0]["source"] == "amazon_jobs:india_software_development", "Amazon source missing")
    check(jobs[0]["url"] == "https://www.amazon.jobs/en/jobs/123/software-development-engineer-i", "Amazon job URL should be canonical")
    params = get_mock.call_args_list[0].kwargs["params"]
    # The earlier expectation (`country[]`) came from a mocked test; live validation
    # on 14 Nov showed amazon.jobs ignores it (2,637 worldwide hits) and only
    # `normalized_country_code[]` restricts results to India (364 hits).
    check(params["normalized_country_code[]"] == "IND" and params["category[]"] == "software-development", "Amazon search must be restricted to India software roles")
    check("country[]" not in params and "industry_experience[]" not in params and "industry_experience" not in params,
          "Amazon default search must not use the ignored country filter or the unreliable experience-band filter")


def test_india_and_remote_location_policy() -> None:
    check(is_india_or_remote_eligible({"location": ["Hyderabad, Telangana, India"]})[0], "India city should pass")
    check(is_india_or_remote_eligible({"location": ["Remote - India"]})[0], "Remote India should pass")
    check(is_india_or_remote_eligible({"location": ["Remote"]})[0], "Undetermined remote eligibility should remain reviewable")
    check(not is_india_or_remote_eligible({"location": ["Remote - United States"]})[0], "US-only remote should be excluded")
    check(not is_india_or_remote_eligible({"location": ["Berlin, Germany"]})[0], "Foreign onsite role should be excluded")
    check(not is_india_or_remote_eligible({"location": []})[0], "Missing location should be excluded")



def test_oracle_hcm_candidate_experience_feed() -> None:
    collector = OracleHCMCollector(
        base_url="https://tenant.fa.ocs.oraclecloud.com",
        site_number="UberCareers",
        company_name="Uber",
        page_size=1,
        max_pages=2,
    )
    first = {"items": [{"requisitionList": [{
        "Id": "JR-101", "Title": "Software Engineer I",
        "PrimaryLocation": "Hyderabad, Telangana, India",
        "ExternalUrlSeo": "https://tenant.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/job/JR-101",
        "PostedDate": "2026-11-01", "ShortDescriptionStr": "1+ years of professional software experience.",
    }]}]}
    second = {"items": [{"requisitionList": [{
        "Id": "JR-102", "Title": "Backend Engineer",
        "PrimaryLocation": "Bengaluru, Karnataka, India",
        "ExternalUrl": "/hcmUI/CandidateExperience/en/sites/UberCareers/job/JR-102",
    }]}]}
    with patch.object(collector.session, "get", side_effect=[FakeResponse(first), FakeResponse(second)]) as get_mock:
        jobs = collector.collect()
    check(len(jobs) == 2, "Oracle HCM collector should paginate through requisitionList")
    check(jobs[0]["source"] == "oracle_hcm:ubercareers", "Oracle HCM source identifier missing")
    check(jobs[0]["external_id"] == "JR-101", "Oracle requisition ID missing")
    check(get_mock.call_args_list[0].kwargs["params"]["onlyData"] == "true", "Oracle query should use Candidate Experience JSON route")


def test_ats_discovery_identifies_supported_platforms() -> None:
    html = """
    <a href='https://jobs.lever.co/example'>Lever</a>
    <a href='https://jobs.ashbyhq.com/sample'>Ashby</a>
    <a href='https://boards.greenhouse.io/acme'>Greenhouse</a>
    <a href='https://jobs.smartrecruiters.com/example'>SmartRecruiters</a>
    <a href='https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite'>Workday</a>
    <a href='https://iaziqy.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/jobs'>Oracle HCM</a>
    """
    found = detect_ats_links(html, "https://company.example/careers")
    providers = {item["provider"] for item in found}
    check(providers == {"lever", "ashby", "greenhouse", "smartrecruiters", "workday", "oracle_hcm"}, "ATS discovery missed a known provider")
    workday = next(item for item in found if item["provider"] == "workday")
    check(workday["tenant"] == "nvidia" and workday["site"] == "NVIDIAExternalCareerSite", "Workday tenant/site parsing failed")



def test_detected_ats_mapping_is_configured_but_not_auto_verified() -> None:
    source = {
        "provider": "oracle_hcm",
        "identifier": "tenant.fa.ocs.oraclecloud.com:UberCareers",
        "base_url": "https://tenant.fa.ocs.oraclecloud.com",
        "site_number": "UberCareers",
        "language": "en",
        "url": "https://tenant.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/UberCareers/jobs",
    }
    config = integration_config_from_source(source)
    check(config is not None, "Oracle HCM source should convert into an integration config")
    check(config["verified"] is False, "ATS discovery must never auto-verify a new provider mapping")
    check(config["status"] == "configured_needs_live_validation", "Candidate mapping should require live validation")
    check(config["settings"]["site_number"] == "UberCareers", "Oracle HCM site number missing")
    check(integration_config_from_source({"provider": "unknown", "identifier": "x"}) is None, "Unknown provider should not be configured")


def test_target_role_policy_matches_engineering_and_rejects_other_roles() -> None:
    check(is_target_software_role("Software Development Engineer I", "1+ years of experience")[0], "SDE I should be eligible")
    check(is_target_software_role("Backend Engineer", "2-4 years of experience")[0], "2-year minimum experience should be eligible")
    check(is_target_software_role("Data Engineer", "Build data pipelines")[0], "Data Engineer should be eligible")
    check(not is_target_software_role("Tech Support (Hybrid)", "Resolve customer issues")[0], "Support should be rejected")
    check(not is_target_software_role("Talent Acquisition Partner", "Recruiting")[0], "Recruiting should be rejected")
    check(not is_target_software_role("Senior Software Engineer", "1 year experience")[0], "Senior title should be rejected")
    check(not is_target_software_role("Software Engineer", "Basic qualifications: 3+ years of professional experience")[0], "3+ year minimum should be rejected")
    check(extract_minimum_experience_years("Minimum qualifications: 2-4 years of professional experience") == 2.0, "Experience range should use its lower bound")



def test_discovery_recognizes_more_ats_but_does_not_claim_support() -> None:
    html = """
    <a href='https://acme.icims.com/jobs/123'>iCIMS</a>
    <a href='https://jobs.example.successfactors.com/career?company=example'>SuccessFactors</a>
    <a href='https://example.taleo.net/careersection/external/jobdetail.ftl'>Taleo</a>
    <a href='https://jobs.jobvite.com/example/job/123'>Jobvite</a>
    <a href='https://example.bamboohr.com/careers/123'>BambooHR</a>
    <a href='https://example.recruitee.com/o/software-engineer'>Recruitee</a>
    <a href='https://example.teamtailor.com/jobs/123'>Teamtailor</a>
    """
    found = detect_ats_links(html, "https://company.example/careers")
    providers = {item["provider"] for item in found}
    expected = {"icims", "successfactors", "taleo", "jobvite", "bamboohr", "recruitee", "teamtailor"}
    check(providers == expected, f"Discovery did not find all ATS links: {providers}")
    check(all(integration_config_from_source(item) is None for item in found), "Discovery-only ATS must not be configured as a supported API connector")


def main() -> int:
    tests = [
        ("30-company registry and candidate requirements", test_registry_has_all_30_unique_target_companies),
        ("Ashby public job board mapping and deduplication", test_ashby_public_job_board_normalization_and_deduplication),
        ("Amazon official India software search mapping", test_amazon_public_search_normalization_and_experience_bands),
        ("India and remote location eligibility", test_india_and_remote_location_policy),
        ("SmartRecruiters pagination and normalization", test_smartrecruiters_pagination_and_normalization),
        ("Workday CXS search and detail normalization", test_workday_search_and_detail_normalization),
        ("Oracle HCM Candidate Experience feed", test_oracle_hcm_candidate_experience_feed),
        ("ATS source discovery across supported platforms", test_ats_discovery_identifies_supported_platforms),
        ("Broader ATS detection never implies unsupported connector support", test_discovery_recognizes_more_ats_but_does_not_claim_support),
        ("Discovered ATS mappings stay unverified until live validation", test_detected_ats_mapping_is_configured_but_not_auto_verified),
        ("0-2 year software-role eligibility policy", test_target_role_policy_matches_engineering_and_rejects_other_roles),
    ]
    passed = failed = 0
    print("=" * 72)
    print("JobPilot 30-Company Integration Tests")
    print("=" * 72)
    for index, (label, test) in enumerate(tests, start=1):
        try:
            test()
            passed += 1
            print(f"Test {index}: PASS - {label}")
        except Exception as exc:
            failed += 1
            print(f"Test {index}: FAIL - {label}: {type(exc).__name__}: {exc}")
    print(f"\nUnit tests: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
