"""Application funnel analytics computed from real records only.

Counts always come straight from the database. Percentages are shown only when there are at
least MIN_APPLIED_FOR_RATES applications, because a rate over a handful of applications is
noise; below that the response says why the rates are hidden instead of printing them.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

MIN_APPLIED_FOR_RATES = 10
TERMINAL = ("offer", "rejected", "withdrawn")


def _tables(session: Session) -> set[str]:
    return set(inspect(session.get_bind()).get_table_names())


def _rate(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def build_funnel(session: Session, *, today: date | None = None, upcoming_limit: int = 20) -> dict[str, Any]:
    today = today or date.today()
    tables = _tables(session)
    empty = {
        "tracked": 0, "prepared": 0, "applied": 0, "responded": 0, "assessments": 0,
        "interviews": 0, "offers": 0, "rejections": 0,
    }
    if "applications" not in tables:
        return {"counts": empty, "rates": None, "rates_hidden_reason": "No applications are tracked yet.",
                "by_company": [], "by_source": [], "upcoming_follow_ups": [], "min_applied_for_rates": MIN_APPLIED_FOR_RATES}

    has_history = "application_status_history" in tables

    def reached(status: str) -> str:
        # An application "reached" a stage if it ever had that status (history) or has it now.
        if has_history:
            return (f"(SELECT COUNT(*) FROM applications a WHERE a.status = '{status}' OR EXISTS "
                    f"(SELECT 1 FROM application_status_history h WHERE h.application_id = a.id AND h.to_status = '{status}'))")
        return f"(SELECT COUNT(*) FROM applications a WHERE a.status = '{status}')"

    row = session.execute(text(f"""
        SELECT
          (SELECT COUNT(*) FROM applications) AS tracked,
          (SELECT COUNT(*) FROM applications WHERE status NOT IN ('saved', 'preparing') OR applied_at IS NOT NULL) AS prepared,
          (SELECT COUNT(*) FROM applications WHERE applied_at IS NOT NULL) AS applied,
          {reached('assessment')} AS assessments,
          {reached('interview')} AS interviews,
          {reached('offer')} AS offers,
          {reached('rejected')} AS rejections
    """)).mappings().one()
    responded = int(session.execute(text(
        "SELECT COUNT(*) FROM applications WHERE applied_at IS NOT NULL AND (status IN ('assessment','interview','offer','rejected')"
        + (" OR EXISTS (SELECT 1 FROM application_status_history h WHERE h.application_id = applications.id AND h.to_status IN ('assessment','interview','offer','rejected'))" if has_history else "")
        + ")"
    )).scalar() or 0)
    counts = {key: int(row[key]) for key in ("tracked", "prepared", "applied", "assessments", "interviews", "offers", "rejections")}
    counts["responded"] = responded

    applied = counts["applied"]
    rates: dict[str, float | None] | None = None
    hidden_reason: str | None = None
    if applied >= MIN_APPLIED_FOR_RATES:
        rates = {
            "response_rate": _rate(responded, applied), "assessment_rate": _rate(counts["assessments"], applied),
            "interview_rate": _rate(counts["interviews"], applied), "offer_rate": _rate(counts["offers"], applied),
            "rejection_rate": _rate(counts["rejections"], applied),
        }
    else:
        hidden_reason = (f"Only {applied} submitted application(s). Percentages stay hidden until there are at least "
                         f"{MIN_APPLIED_FOR_RATES}, because rates over so few applications would mislead.")

    by_company = [
        {"company": r["company"], "applied": int(r["applied"]), "responded": int(r["responded"]),
         "interviews": int(r["interviews"]), "offers": int(r["offers"])}
        for r in session.execute(text("""
            SELECT c.name AS company,
                   SUM(CASE WHEN a.applied_at IS NOT NULL THEN 1 ELSE 0 END) AS applied,
                   SUM(CASE WHEN a.status IN ('assessment','interview','offer','rejected') THEN 1 ELSE 0 END) AS responded,
                   SUM(CASE WHEN a.status IN ('interview','offer') THEN 1 ELSE 0 END) AS interviews,
                   SUM(CASE WHEN a.status = 'offer' THEN 1 ELSE 0 END) AS offers
            FROM applications a JOIN jobs j ON j.id = a.job_id JOIN companies c ON c.id = j.company_id
            GROUP BY c.name HAVING applied > 0 ORDER BY applied DESC, c.name
        """)).mappings()
    ]
    by_source = [
        {"source": r["source"], "applied": int(r["applied"]), "responded": int(r["responded"])}
        for r in session.execute(text("""
            SELECT j.source AS source,
                   SUM(CASE WHEN a.applied_at IS NOT NULL THEN 1 ELSE 0 END) AS applied,
                   SUM(CASE WHEN a.status IN ('assessment','interview','offer','rejected') THEN 1 ELSE 0 END) AS responded
            FROM applications a JOIN jobs j ON j.id = a.job_id
            GROUP BY j.source HAVING applied > 0 ORDER BY applied DESC
        """)).mappings()
    ]
    upcoming = [
        {"application_id": r["id"], "title": r["title"], "company": r["company"], "status": r["status"],
         "follow_up_date": r["follow_up_date"], "next_action": r["next_action"], "overdue": r["follow_up_date"] < today.isoformat()}
        for r in session.execute(text("""
            SELECT a.id, j.title, c.name AS company, a.status, a.follow_up_date, a.next_action
            FROM applications a JOIN jobs j ON j.id = a.job_id JOIN companies c ON c.id = j.company_id
            WHERE a.follow_up_date IS NOT NULL AND TRIM(a.follow_up_date) <> ''
              AND a.status NOT IN ('offer','rejected','withdrawn')
            ORDER BY a.follow_up_date LIMIT :limit
        """), {"limit": upcoming_limit}).mappings()
    ]
    return {
        "counts": counts, "rates": rates, "rates_hidden_reason": hidden_reason, "min_applied_for_rates": MIN_APPLIED_FOR_RATES,
        "by_company": by_company, "by_source": by_source, "upcoming_follow_ups": upcoming,
        "note": "Counts come from your own tracked applications; nothing is estimated.",
    }
