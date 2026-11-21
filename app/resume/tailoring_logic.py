"""What "tailored for this job" actually does, without changing a single word of your resume.

Your wording is never rewritten (that would risk claims you did not make). Tailoring is everything else a
careful person does for a specific posting:

1. Bullets inside each job and project are ordered so the ones that match the posting's technologies come first
   (a bullet that refers back to the one before it, such as "that pipeline", stays right after it).
2. Jobs and projects are ordered by how well they match the posting.
3. A "Relevant to this role" line lists your verified skills that the posting asks for, first in Technical Skills,
   so both a person skimming and a keyword scanner see them straight away.
4. If the result would run past one page, the least relevant bullets are dropped (never below three per job and
   two per project) until it fits, like your master resume.
5. Every change is listed in the report, so you can see exactly what differs from your master resume.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any

from app.resume.resume_parser import TECHNOLOGY_ALIASES

MIN_BULLETS_EXPERIENCE = 3
MIN_BULLETS_PROJECT = 2
_REFERS_BACK = re.compile(
    r"\b(?:that|this|these|those)\s+(?:pipeline|service|services|migration|project|system|tool|workflow|platform|loop|module|modules|repository|repositories)\b",
    re.IGNORECASE,
)


@dataclass
class TailoredContent:
    records: list[dict[str, Any]]
    matches: list[str] = field(default_factory=list)  # verified skills the posting asks for, required first
    changes: list[str] = field(default_factory=list)  # plain-language list of what differs from the master resume


def _variants(term: str) -> set[str]:
    """The term and its known spellings ("REST APIs" also matches "REST API")."""
    lowered = term.casefold().strip()
    found = {lowered}
    for canonical, aliases in TECHNOLOGY_ALIASES.items():
        names = {canonical.casefold(), *(alias.casefold() for alias in aliases)}
        if lowered in names:
            found |= names
    return {name for name in found if name}


def _contains(text: str, variants: set[str]) -> bool:
    return any(re.search(rf"(?<![a-z0-9+#]){re.escape(name)}(?![a-z0-9+#])", text) for name in variants)


class JobTerms:
    """The posting's technologies, split by how much they matter."""

    def __init__(self, selection: dict[str, Any]) -> None:
        signals = selection.get("signals") if isinstance(selection.get("signals"), dict) else {}
        self.required = [str(t) for t in signals.get("required_skills") or []]
        self.preferred = [str(t) for t in signals.get("preferred_skills") or []]
        self.inferred = [str(t) for t in signals.get("inferred_job_technologies") or []]
        self._variants = {term: _variants(term) for term in {*self.required, *self.preferred, *self.inferred}}

    def score(self, text: str) -> tuple[int, list[str]]:
        lowered = " ".join(str(text).split()).casefold()
        matched: list[str] = []
        points = 0
        for terms, weight in ((self.required, 3), (self.preferred, 2), (self.inferred, 1)):
            for term in terms:
                if term not in matched and _contains(lowered, self._variants[term]):
                    matched.append(term)
                    points += weight
        return points, matched


def order_bullets(bullets: list[str], terms: JobTerms) -> tuple[list[str], int]:
    """Most relevant first. A bullet that points back at the previous one stays attached to it."""
    units: list[list[int]] = []
    for index, bullet in enumerate(bullets):
        if index > 0 and _REFERS_BACK.search(bullet) and units:
            units[-1].append(index)
        else:
            units.append([index])
    scored = [(max(terms.score(bullets[i])[0] for i in unit), unit) for unit in units]
    ordered_units = sorted(scored, key=lambda pair: (-pair[0], pair[1][0]))
    result = [bullets[i] for _, unit in ordered_units for i in unit]
    moved = sum(1 for before, after in zip(bullets, result) if before != after)
    return result, moved


def _bullets(record: dict[str, Any]) -> list[str]:
    bullets = (record.get("metadata") or {}).get("bullets")
    return [str(b) for b in bullets] if isinstance(bullets, list) else []


def _entry_score(record: dict[str, Any], terms: JobTerms) -> int:
    return sum(sorted((terms.score(b)[0] for b in _bullets(record)), reverse=True)[:3])


def _short(text: str, limit: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _order_and_trim(records: list[dict[str, Any]], terms: JobTerms, changes: list[str]) -> list[dict[str, Any]]:
    records = copy.deepcopy(records)
    for category, label in (("experience", "job"), ("project", "project")):
        entries = [r for r in records if r.get("category") == category]
        if not entries:
            continue
        for record in entries:
            bullets = _bullets(record)
            ordered, moved = order_bullets(bullets, terms)
            if moved:
                record["metadata"]["bullets"] = ordered
                first_score, first_terms = terms.score(ordered[0])
                changes.append(
                    f"Moved the bullets that match this job to the top of \"{_short(str(record.get('title') or label), 50)}\""
                    + (f" (first bullet matches {', '.join(first_terms[:4])})" if first_terms else "") + "."
                )
        if len(entries) > 1:
            scored = sorted(range(len(entries)), key=lambda i: (-_entry_score(entries[i], terms), i))
            if scored != list(range(len(entries))):
                names = [str(entries[i].get("title")) for i in scored]
                changes.append(f"Ordered the {label}s by match to this job: " + ", then ".join(f'"{_short(n, 40)}"' for n in names) + ".")
            ordered_entries = [entries[i] for i in scored]
            slots = iter(ordered_entries)
            records = [next(slots) if r.get("category") == category else r for r in records]
    return records


def _trim_to_one_page(records: list[dict[str, Any]], candidate: dict[str, Any], terms: JobTerms, changes: list[str], matches: list[str]) -> list[dict[str, Any]]:
    from app.resume.resume_layout import build_layout
    from app.resume.resume_pdf_builder import page_count

    dropped: list[str] = []
    while page_count(build_layout(records, candidate, matches)) > 1:
        candidates = []
        for record in records:
            floor = MIN_BULLETS_EXPERIENCE if record.get("category") == "experience" else MIN_BULLETS_PROJECT if record.get("category") == "project" else None
            bullets = _bullets(record)
            if floor is None or len(bullets) <= floor:
                continue
            # only a trailing bullet can go, so a bullet that others point back to is never separated from them
            last = bullets[-1]
            candidates.append((terms.score(last)[0], record, last))
        if not candidates:
            break
        _, record, bullet = min(candidates, key=lambda item: item[0])
        record["metadata"]["bullets"] = _bullets(record)[:-1]
        dropped.append(bullet)
    if dropped:
        changes.append(f"Dropped {len(dropped)} least relevant bullet(s) so the resume stays on one page, like your master: "
                       + "; ".join(f'"{_short(d, 60)}"' for d in dropped[:3]) + ("; …" if len(dropped) > 3 else ""))
    return records


def tailor_for_job(selection: dict[str, Any], store: dict[str, Any], *, fit_one_page: bool = True) -> TailoredContent:
    """The content for this job: verified records, ordered for the posting, with a list of what changed."""
    from app.resume.resume_builder import ResumeBuildError, _validated_records

    candidate = store.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("name"):
        raise ResumeBuildError("Evidence store has no candidate name.")
    terms = JobTerms(selection)
    changes: list[str] = []
    records = _order_and_trim(_validated_records(selection, store), terms, changes)

    wanted: list[tuple[int, int, str]] = []
    for position, record in enumerate(records):
        if record.get("category") != "skill":
            continue
        meta = record.get("metadata") or {}
        shown = str(meta.get("print_text") or record.get("title") or "").strip()
        _, found = terms.score(shown)
        if any(term in terms.required for term in found):
            wanted.append((0, position, shown))
        elif any(term in terms.preferred for term in found):
            wanted.append((1, position, shown))
    matches = list(dict.fromkeys(name for _, _, name in sorted(wanted) if name))
    if matches:
        changes.append("Added a \"Relevant to this role\" line at the top of Technical Skills: " + ", ".join(matches[:8]) + ("…" if len(matches) > 8 else "") + ".")

    if fit_one_page:
        records = _trim_to_one_page(records, candidate, terms, changes, matches)
    changes.append("The wording of every bullet is exactly as in your master resume; nothing was rewritten or added.")
    return TailoredContent(records=records, matches=matches, changes=changes)


__all__ = ["JobTerms", "TailoredContent", "order_bullets", "tailor_for_job"]
