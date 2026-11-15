"""Side-by-side comparison of several jobs, built from their stored match data."""
from __future__ import annotations

from typing import Any


def build_comparison(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare 2-4 jobs.

    Each entry needs: id, title, company, and ``match`` (the serialized match dict).
    Returns the rows plus highlights: the best overall score, a skill matrix (required skills across the
    jobs and whether the profile covers each), skills missing everywhere, and each job's blockers.
    """
    if len(entries) < 2:
        raise ValueError("At least two jobs are needed to compare.")

    rows: list[dict[str, Any]] = []
    skill_matrix: dict[str, dict[int, str]] = {}
    for entry in entries:
        match = entry.get("match") or {}
        job_id = entry["id"]
        required = [str(s) for s in match.get("required_skills") or []]
        matched = {str(s).lower() for s in match.get("matched_required_skills") or []}
        for skill in required:
            skill_matrix.setdefault(skill, {})[job_id] = "matched" if skill.lower() in matched else "missing"
        mismatches = match.get("mismatches") or {}
        eligibility = match.get("eligibility") or {}
        blockers = list(mismatches.get("mandatory_requirement_mismatch") or [])
        if eligibility.get("status") == "excluded":
            blockers = [f"Excluded by eligibility policy: {', '.join(eligibility.get('reasons') or ['see job'])}"] + blockers
        rows.append({
            "id": job_id,
            "title": entry.get("title"),
            "company": entry.get("company"),
            "location": entry.get("location"),
            "url": entry.get("url"),
            "score": match.get("score"),
            "recommendation": match.get("recommendation"),
            "required_years": match.get("required_years"),
            "score_breakdown": match.get("score_breakdown") or {},
            "compensation": entry.get("compensation"),
            "blockers": blockers,
            "experience_mismatch": list(mismatches.get("experience_mismatch") or []),
            "location_mismatch": list(mismatches.get("location_mismatch") or []),
            "preferred_missing": list(mismatches.get("preferred_skill_missing") or []),
            "reasons": list(match.get("reasons") or []),
        })

    scored = [r for r in rows if isinstance(r["score"], (int, float))]
    best = max(scored, key=lambda r: r["score"]) if scored else None
    matrix = [
        {"skill": skill, "jobs": {str(job_id): status for job_id, status in per_job.items()},
         "required_by": len(per_job), "covered_by_profile": sum(1 for s in per_job.values() if s == "matched")}
        for skill, per_job in skill_matrix.items()
    ]
    matrix.sort(key=lambda item: (-item["required_by"], item["skill"].lower()))
    return {
        "jobs": rows,
        "highlights": {
            "best_overall_job_id": best["id"] if best else None,
            "best_overall_score": best["score"] if best else None,
            "skill_matrix": matrix,
            "skills_missing_everywhere": [m["skill"] for m in matrix if m["covered_by_profile"] == 0],
            "jobs_with_blockers": [r["id"] for r in rows if r["blockers"]],
        },
    }
