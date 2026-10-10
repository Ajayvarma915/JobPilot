from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from app.resume.evidence_store import DEFAULT_STORE_PATH, MasterResumeEvidenceStore
from app.resume.resume_parser import TECHNOLOGY_ALIASES, extract_technologies


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "of", "on", "or",
    "our", "that", "the", "their", "this", "to", "using", "with", "you",
    "your", "will", "work", "working", "years", "year", "experience",
    "software", "engineer", "engineering", "developer", "development",
    "ability", "team", "teams", "role", "responsibilities", "responsibility",
}

CATEGORY_LIMITS = {
    "skill": 12,
    "project": 3,
    "experience": 2,
    "education": 1,
    "certification": 3,
    "achievement": 2,
}

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")


def _clean_list(values: Iterable[str] | None) -> list[str]:
    if values is None:
        return []

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()

        if cleaned and cleaned.casefold() not in seen:
            result.append(cleaned)
            seen.add(cleaned.casefold())

    return result


def _canonical_skill(value: str) -> str:
    wanted = re.sub(r"\s+", " ", value).strip().casefold()

    for canonical, aliases in TECHNOLOGY_ALIASES.items():
        if wanted == canonical.casefold() or any(
            wanted == alias.casefold() for alias in aliases
        ):
            return canonical

    recognized = extract_technologies(value)
    return recognized[0] if len(recognized) == 1 else value.strip()


def _canonical_skills(values: Iterable[str] | None) -> list[str]:
    return _clean_list(_canonical_skill(value) for value in (values or []))


def _extract_technologies_safely(text: str) -> list[str]:
    """Detect technologies without reading the .js suffix as JavaScript.

    Short aliases such as JS and TS are accepted as standalone tokens,
    but a preceding dot blocks them. This prevents Next.js and Auth.js
    from being interpreted as separate JavaScript skill evidence.
    """
    matches: list[tuple[int, str]] = []

    for canonical, aliases in TECHNOLOGY_ALIASES.items():
        positions: list[int] = []

        for alias in aliases:
            if alias.casefold() in {"js", "ts"}:
                pattern = re.compile(
                    rf"(?<![A-Za-z0-9+#.]){re.escape(alias)}(?![A-Za-z0-9+#])",
                    re.IGNORECASE,
                )
            else:
                pattern = re.compile(
                    rf"(?<![A-Za-z0-9+#]){re.escape(alias)}(?![A-Za-z0-9+#])",
                    re.IGNORECASE,
                )

            found = pattern.search(text)

            if found:
                positions.append(found.start())

        if positions:
            matches.append((min(positions), canonical))

    matches.sort(key=lambda item: item[0])
    return _clean_list(name for _, name in matches)


def _tokens(text: str) -> set[str]:
    return {
        token.casefold().strip(".-")
        for token in TOKEN_RE.findall(text)
        if len(token.strip(".-")) >= 3
        and token.casefold().strip(".-") not in STOPWORDS
    }


def _evidence_skill_names(item: dict[str, Any]) -> set[str]:
    # A skill record can point to an entire skills-section line.
    # Use its own title to avoid importing neighboring skills.
    if item.get("category") == "skill" and item.get("title"):
        return {_canonical_skill(str(item["title"])).casefold()}

    text_parts = [
        str(item.get("title", "")),
        str(item.get("statement", "")),
        str(item.get("source", {}).get("text", "")),
    ]

    # Do not trust parser-derived metadata for skill matching: older metadata
    # may contain a false JavaScript match extracted from Next.js or Auth.js.
    recognized = _extract_technologies_safely("\n".join(text_parts))
    return {name.casefold() for name in recognized}


def _evidence_tokens(item: dict[str, Any]) -> set[str]:
    metadata = item.get("metadata", {})
    tech = " ".join(
        str(value) for value in metadata.get("technologies", []) or []
    )

    if item.get("category") == "skill":
        # Score each skill record using its own title, not neighboring skills.
        text = str(item.get("title", ""))
    else:
        text = " ".join(
            [
                str(item.get("title", "")),
                str(item.get("statement", "")),
                str(item.get("source", {}).get("text", "")),
                tech,
            ]
        )

    return _tokens(text)


def _category_weight(category: str, kind: str) -> float:
    weights = {
        "required": {
            "skill": 16.0,
            "project": 12.0,
            "experience": 10.0,
            "education": 3.0,
            "certification": 3.0,
            "achievement": 2.0,
        },
        "preferred": {
            "skill": 9.0,
            "project": 8.0,
            "experience": 7.0,
            "education": 3.0,
            "certification": 4.0,
            "achievement": 2.0,
        },
        "inferred": {
            "skill": 6.0,
            "project": 7.0,
            "experience": 5.0,
            "education": 1.0,
            "certification": 2.0,
            "achievement": 1.0,
        },
    }

    return weights.get(kind, {}).get(category, 1.0)


class ResumeEvidenceSelector:
    """Rank resume evidence against a JD without inventing new claims.

    Only evidence explicitly verified by the user is put in
    selected_evidence. Relevant unverified records go to review_queue.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        self.store = MasterResumeEvidenceStore(store_path or DEFAULT_STORE_PATH)

    def select_for_job(
        self,
        *,
        job_title: str,
        job_description: str,
        required_skills: Iterable[str] | None = None,
        preferred_skills: Iterable[str] | None = None,
        max_skills: int = 12,
        max_projects: int = 3,
        max_experience: int = 2,
        max_certifications: int = 3,
        max_achievements: int = 2,
    ) -> dict[str, Any]:
        if not job_title.strip():
            raise ValueError("job_title must not be empty")

        if not job_description.strip():
            raise ValueError("job_description must not be empty")

        required = _canonical_skills(required_skills)
        required_keys = {item.casefold() for item in required}

        preferred = [
            skill
            for skill in _canonical_skills(preferred_skills)
            if skill.casefold() not in required_keys
        ]

        detected_from_jd = _canonical_skills(
            _extract_technologies_safely(
                f"{job_title}\n{job_description}"
            )
        )

        explicit = {
            skill.casefold()
            for skill in required + preferred
        }

        inferred = [
            skill
            for skill in detected_from_jd
            if skill.casefold() not in explicit
        ]

        jd_text = f"{job_title}\n{job_description}"
        jd_tokens = _tokens(jd_text)
        title_tokens = _tokens(job_title)
        candidates: list[dict[str, Any]] = []

        for item in self.store.load()["evidence"]:
            category = str(item.get("category", ""))
            skills = _evidence_skill_names(item)

            matched_required = [
                skill for skill in required if skill.casefold() in skills
            ]
            matched_preferred = [
                skill for skill in preferred if skill.casefold() in skills
            ]
            matched_inferred = [
                skill for skill in inferred if skill.casefold() in skills
            ]

            item_tokens = _evidence_tokens(item)
            generic_overlap = sorted(jd_tokens & item_tokens)
            title_overlap = sorted(title_tokens & item_tokens)

            score = (
                len(matched_required) * _category_weight(category, "required")
                + len(matched_preferred) * _category_weight(category, "preferred")
                + len(matched_inferred) * _category_weight(category, "inferred")
            )

            # Text overlap is only a secondary ranking signal for larger items.
            # Individual skill records require exact canonical skill matches.
            if category != "skill":
                score += min(len(title_overlap), 3) * (
                    2.0 if category in {"project", "experience"} else 0.5
                )
                score += min(len(generic_overlap), 5) * (
                    0.6 if category in {"project", "experience"} else 0.15
                )

            score = round(score, 2)

            if score <= 0:
                continue

            review = item.get("review", {})
            is_verified = bool(review.get("user_verified", False))
            reasons: list[str] = []

            if matched_required:
                reasons.append(
                    "matches required skills: " + ", ".join(matched_required)
                )

            if matched_preferred:
                reasons.append(
                    "matches preferred skills: " + ", ".join(matched_preferred)
                )

            if matched_inferred:
                reasons.append(
                    "matches JD technology terms: " + ", ".join(matched_inferred)
                )

            if title_overlap:
                reasons.append(
                    "overlapping role/project terms: " + ", ".join(title_overlap)
                )

            candidates.append(
                {
                    "evidence_id": item.get("evidence_id"),
                    "category": category,
                    "title": item.get("title", ""),
                    "statement": item.get("statement", ""),
                    "source": item.get("source", {}),
                    "metadata": item.get("metadata", {}),
                    "score": score,
                    "matched_required_skills": matched_required,
                    "matched_preferred_skills": matched_preferred,
                    "matched_job_technologies": matched_inferred,
                    "text_overlap_terms": generic_overlap[:10],
                    "reason": reasons or ["matched wording in job description"],
                    "user_verified": is_verified,
                    "review_status": review.get("status", "needs_review"),
                    "eligible_for_resume": is_verified,
                }
            )

        candidates.sort(
            key=lambda item: (
                item["score"],
                item["category"] == "project",
                item["title"].casefold(),
            ),
            reverse=True,
        )

        limits = {
            "skill": max(0, max_skills),
            "project": max(0, max_projects),
            "experience": max(0, max_experience),
            "education": 1,
            "certification": max(0, max_certifications),
            "achievement": max(0, max_achievements),
        }

        counts: dict[str, int] = {}
        selected: list[dict[str, Any]] = []
        review_queue: list[dict[str, Any]] = []

        for candidate in candidates:
            category = candidate["category"]

            if candidate["user_verified"]:
                current_count = counts.get(category, 0)

                if current_count < limits.get(category, 0):
                    selected.append(candidate)
                    counts[category] = current_count + 1
            else:
                review_queue.append(candidate)

        selected_required = {
            skill.casefold()
            for item in selected
            for skill in item["matched_required_skills"]
        }

        review_required = {
            skill.casefold()
            for item in review_queue
            for skill in item["matched_required_skills"]
        }

        required_by_key = {
            skill.casefold(): skill for skill in required
        }

        selected_coverage = [
            required_by_key[key]
            for key in required_by_key
            if key in selected_required
        ]

        awaiting_review = [
            required_by_key[key]
            for key in required_by_key
            if key not in selected_required and key in review_required
        ]

        uncovered = [
            required_by_key[key]
            for key in required_by_key
            if key not in selected_required and key not in review_required
        ]

        return {
            "job": {"title": job_title.strip()},
            "signals": {
                "required_skills": required,
                "preferred_skills": preferred,
                "inferred_job_technologies": inferred,
            },
            "coverage": {
                "required_skills": len(required),
                "verified_covered": selected_coverage,
                "awaiting_evidence_review": awaiting_review,
                "not_found_in_evidence": uncovered,
            },
            "selected_evidence": selected,
            "review_queue": review_queue,
            "counts": {
                "verified_selected": len(selected),
                "unverified_relevant_for_review": len(review_queue),
            },
            "safety": {
                "only_user_verified_records_selected": True,
                "unverified_records_are_suggestions_only": True,
                "generated_claims": False,
            },
        }


__all__ = ["ResumeEvidenceSelector"]