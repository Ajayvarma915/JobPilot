# Architecture

JobPilot is a FastAPI backend with a SQLite database, a React + TypeScript frontend, a Manifest V3 Chrome extension and an optional local Ollama model. Nothing leaves your machine except the requests to public career sites and (if you connect it) the read-only Gmail API.

```
career sites ──► collectors ──► eligibility ──► database ──► matching ──► recommendations
 (public APIs)   (per ATS)      (one rule set)   (jobs,        (explainable)   (next actions)
                                                  versions)         │
                                                                    ▼
 Chrome extension ◄── tracker ◄── documents ◄── evidence store ◄── local AI (optional)
 (fills, never       (readiness,  (resume,       (only what you
  submits)            history)     cover letter,   verified)
                                   answers)
 Gmail (read-only) ──► classify + strict match ──► pending event ──► YOU approve ──► status changes
```

## Backend modules (`app/`)

| Module | Responsibility |
|---|---|
| `collectors/` | One class per source type (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle HCM, Amazon, Atlassian, Google). Each returns normalised job dicts and tolerates per-job failures. |
| `services/target_role_policy.py` | **The single source of truth for eligibility**: role family, seniority, PhD, experience, country. `evaluate_eligibility()` returns eligible / eligible_needs_review / excluded / source_unverified with reasons. Everything else calls it. |
| `services/source_health.py` | Maps registry entries to explicit source states and records fetch history. A configured source is never treated as verified. |
| `db/` | SQLAlchemy models and `JobRepository` (change detection, version history, removal detection). One function, `resolve_database_path()`, decides which database file is used. |
| `services/job_matcher.py`, `jd_analyzer.py`, `match_weights.py` | The explainable match score, weights from `data/match_weights.json`, and the eligibility cap. |
| `services/opportunities.py` | Next-action rules, opportunity score and skill-gap report. |
| `ai/` | Provider interface (Ollama or off), runner with retry, validation, cache and metadata-only logging, and the fit analysis. |
| `resume/` | Evidence store, selector, DOCX/PDF builders, evaluator, tailoring report and the fail-closed no-fabrication check. |
| `applications/` | Tracker (readiness, status history, follow-ups), profile facts, cover letters, answer library, contacts and interview plans. |
| `email/gmail_integration.py` | Read-only Gmail OAuth, conservative classifier, strict application matching and the approval queue. |
| `services/analytics.py`, `sync_summary.py` | Funnel analytics and the change summary. |
| `api/main.py` | The HTTP API. [API.md](API.md) lists every endpoint. |

## Principles the code enforces

- **Deterministic rules are authoritative.** The model can add wording, never change an eligibility decision or the score shown.
- **No invented facts.** Documents are built from your profile and evidence you verified; anything unsupported is reported, not written.
- **You approve every consequential step.** Application status changes from email wait for your approval; outreach is a draft until you send it yourself; the extension never submits.
- **Fail closed.** An ambiguous email match, a missing date, a corrupt weights file or a resume with an unverified bullet is refused, not guessed.

## Data

SQLite (`jobpilot.db`). SQLAlchemy models cover companies, jobs, job versions, source health, match cache, AI cache, resume versions, cover letters, answers, contacts, interactions and interview items. The tracker and Gmail modules manage their own tables with plain SQL (applications, preparations, profile vault, status history, email events). New tables are created on first use and never dropped. There is no migration framework yet; see [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Frontend (`frontend/src/`)

`App.tsx` holds navigation and shared state; each screen is a file in `views/`; shared pieces are in `components.tsx`, helpers in `lib.tsx`, types in `types.ts`, and the API address (plus optional token) in `config.ts`. There is no URL routing yet.

## Extension (`browser_extension/jobpilot-form-assistant/`)

`field_matcher.js` holds the pure matching rules (no DOM, no network; unit-tested in Node). `popup.js` loads the preparation data from the local API, injects the matcher and fills clearly labelled fields. Permissions are `activeTab` and `scripting` plus the local API address only.
