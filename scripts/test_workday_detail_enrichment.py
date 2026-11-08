from __future__ import annotations

from unittest.mock import patch
import requests

from app.collectors.workday import WorkdayCollector


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_detail_endpoint_appends_external_path_once_and_normalizes_locations():
    collector = WorkdayCollector(
        tenant="nvidia", site="NVIDIAExternalCareerSite", company_name="NVIDIA",
        host="https://nvidia.wd5.myworkdayjobs.com", fetch_details=True, page_size=20,
    )
    external_path = "/job/US-CA-Santa-Clara/Harness-and-Platform-Engineer_JR2021886"
    summary = {"total": 1, "jobPostings": [{
        "title": "Harness and Platform Engineer, AI Safety and Security Engineering",
        "externalPath": external_path, "jobReqId": "JR2021886", "locationsText": "6 Locations",
    }]}
    detail = {"jobPostingInfo": {
        "jobTitle": "Harness and Platform Engineer, AI Safety and Security Engineering",
        "jobDescription": "<p>Build platform tooling and security automation.</p>",
        "location": {"descriptor": "Hyderabad, Telangana, India"},
        "additionalLocations": [
            {"descriptor": "Bengaluru, Karnataka, India"},
            {"descriptor": "Hyderabad, Telangana, India"},
        ],
        "timeType": "Full time",
    }}
    expected_detail_url = f"{collector.api_root}{external_path}"
    with patch.object(collector.session, "post", return_value=FakeResponse(summary)):
        with patch.object(collector.session, "get", return_value=FakeResponse(detail)) as get_mock:
            jobs = collector.collect()
    assert len(jobs) == 1
    assert get_mock.call_args.args[0] == expected_detail_url
    assert jobs[0]["description"] == "Build platform tooling and security automation."
    assert jobs[0]["location"] == ["Hyderabad, Telangana, India", "Bengaluru, Karnataka, India"]
    assert jobs[0]["_jobpilot_detail_fetch_status"] == "fetched"
    assert jobs[0]["url"].startswith(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/"
    )


def test_failed_workday_detail_is_explicitly_auditable():
    collector = WorkdayCollector(
        tenant="nvidia", site="NVIDIAExternalCareerSite", company_name="NVIDIA",
        host="https://nvidia.wd5.myworkdayjobs.com", fetch_details=True,
    )
    summary = {"total": 1, "jobPostings": [{
        "title": "Software Engineer I",
        "externalPath": "/job/India-Hyderabad/Software-Engineer-I_JR123",
        "jobReqId": "JR123", "locationsText": "India, Hyderabad",
    }]}
    with patch.object(collector.session, "post", return_value=FakeResponse(summary)):
        with patch.object(collector.session, "get", side_effect=requests.RequestException("network failure")):
            jobs = collector.collect()
    assert jobs[0]["_jobpilot_detail_fetch_status"] == "failed"


if __name__ == "__main__":
    test_detail_endpoint_appends_external_path_once_and_normalizes_locations()
    test_failed_workday_detail_is_explicitly_auditable()
    print("PASS - Workday detail URL uses externalPath exactly once")
    print("PASS - Workday locations are normalized and deduplicated")
    print("PASS - failed detail requests are explicit in the audit")
