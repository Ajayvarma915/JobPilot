"""Verified candidate facts that cover letters and answers may use.

Facts come only from what the user entered or imported in their profile vault, plus the
salary expectation they typed into an application. Nothing is inferred or invented.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

VAULT_FIELDS = (
    "contact_name", "current_location", "current_employer", "current_title",
    "years_experience", "notice_period", "work_authorization", "requires_sponsorship",
)


def load_profile_facts(session: Session) -> dict[str, str]:
    """Return the non-empty profile facts, or an empty dict when none have been saved yet."""
    tables = set(inspect(session.get_bind()).get_table_names())
    facts: dict[str, str] = {}
    if "candidate_profile_vault" in tables:
        row = session.execute(text("SELECT * FROM candidate_profile_vault WHERE id = 1")).mappings().first()
        if row is not None:
            for field in VAULT_FIELDS:
                value = row.get(field)
                if isinstance(value, str) and value.strip():
                    facts[field] = value.strip()
    if "application_preparations" in tables:
        salary = session.execute(
            text(
                "SELECT salary_expectation FROM application_preparations "
                "WHERE TRIM(COALESCE(salary_expectation, '')) <> '' ORDER BY updated_at DESC LIMIT 1"
            )
        ).scalar()
        if isinstance(salary, str) and salary.strip():
            facts["salary_expectation"] = salary.strip()
    return facts
