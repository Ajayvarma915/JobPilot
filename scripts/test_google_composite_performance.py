from __future__ import annotations

from scripts.sync_target_companies import _CompositeCollector, _make_audit_row
from app.services.target_role_policy import is_target_software_role


# Every Google row marked eligible or eligible_needs_review in the supplied
# v5 audit must survive the title-only preliminary filter.
V5_CANDIDATE_TITLES = [
    "Software Engineer, Security, Privacy, Detection",
    "Software Engineer III, AI/ML Infrastructure, Performance Engineering",
    "Software Engineer III, Core Systems",
    "Software Engineer III, Mobile, Android",
    "Software Engineer III, Security/Privacy, gTech Risk",
    "Software Engineer II, Corp Eng",
    "Software Engineer III, Full Stack, Google Cloud",
    "Software Engineer III, Infrastructure, Google Cloud",
    "Software Engineer III, Networking, GGN WANForms",
    "Software Engineer III, Google Distributed Cloud",
    "Software Engineer II, Google Cloud",
    "Data and AI Engineer",
    "Salesforce Application Engineer, YouTube",
    "Cloud Engineer, Data and AI",
    "Cloud AI Engineer (English)",
]


class FakeGoogleCollector:
    def __init__(self, jobs):
        self.jobs = jobs
        self.enriched_batches = []

    def collect(self):
        return list(self.jobs)

    def enrich_jobs(self, jobs):
        self.enriched_batches.append([job["external_id"] for job in jobs])
        return [
            dict(
                job,
                description="2 years of software engineering experience",
                full_description="loaded-once",
            )
            for job in jobs
        ]


def main() -> int:
    assert all(is_target_software_role(title, "")[0] for title in V5_CANDIDATE_TITLES)

    first = FakeGoogleCollector([
        {"external_id": "1", "url": "https://jobs/1", "title": "Backend Engineer"},
        {"external_id": "2", "url": "https://jobs/2", "title": "Software Engineer II"},
        {"external_id": "3", "url": "https://jobs/3", "title": "Senior Software Engineer"},
        {"external_id": "4", "url": "https://jobs/4", "title": "Software Engineer III"},
    ])
    second = FakeGoogleCollector([
        {"external_id": "1", "url": "https://jobs/1", "title": "Backend Engineer"},
        {"external_id": "5", "url": "https://jobs/5", "title": "Product Manager"},
        {"external_id": "6", "url": "https://jobs/6", "title": "Data Engineer"},
    ])

    results = _CompositeCollector(
        [first, second],
        fetch_details=True,
    ).collect()

    assert [job["external_id"] for job in results] == ["1", "2", "3", "4", "5", "6"]
    # Senior and non-software title exclusions are retained in the audit set,
    # but only in-scope software titles get full detail requests.
    assert first.enriched_batches == [["1", "2", "4", "6"]]
    assert second.enriched_batches == []
    by_id = {job["external_id"]: job for job in results}
    assert all(by_id[key].get("full_description") == "loaded-once" for key in ["1", "2", "4", "6"])
    assert "description" not in by_id["3"]
    assert "description" not in by_id["5"]

    # Engineer III is deliberately included in the preliminary candidate set;
    # its actual experience requirement is assessed after full JD enrichment.
    assert by_id["4"]["full_description"] == "loaded-once"

    skipped_audit = _make_audit_row(
        {"id": "google", "name": "Google", "integration": {
            "provider": "google_careers", "status": "active", "verified": True
        }},
        {
            "external_id": "3", "url": "https://jobs/3",
            "title": "Senior Software Engineer",
            "_jobpilot_detail_fetch_status": "skipped_title_prefilter",
        },
        2.0,
    )
    assert skipped_audit["detail_fetch_status"] == "skipped_title_prefilter"

    no_detail = _CompositeCollector(
        [FakeGoogleCollector([{"external_id": "7", "url": "https://jobs/7", "title": "Software Engineer"}])],
        fetch_details=False,
    ).collect()
    assert len(no_detail) == 1
    assert "full_description" not in no_detail[0]

    print("PASS - cross-query duplicates are removed before enrichment")
    print("PASS - title prefilter skips detail downloads but retains every card for audit")
    print("PASS - Engineer III candidates remain in the detail-fetch set")
    print("PASS - all 15 v5 Google candidate titles survive the title-only prefilter")
    print("PASS - audit CSV records why a job description was not fetched")
    print("PASS - disabling detail fetching keeps the collector cards-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
