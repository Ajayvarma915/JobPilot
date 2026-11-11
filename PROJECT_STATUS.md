# JobPilot — Project Status

_Last updated: 2026-11-09 (session 1: repository audit + role-filter regression repair)._
Status is based on code inspection and test runs. Nothing here is a percentage estimate.

## Safety rules for this repo
- Never open or print `.env`, `credentials/`, `tokens/`, `frontend/.env.local` or the Gmail token files.
- Baseline tests were run in a **sandbox copy** (no secrets, copy of `jobpilot.db`) because several tests write to the DB path hard-coded in `app/db/database.py`.
- Live source sync stays disabled until a source is `verified`. Application submission stays human-controlled.

## Module matrix

| Module | Implemented | Tested (offline) | Real-world verified | Missing / gaps |
|---|---|---|---|---|
| Role/eligibility policy (`app/services/target_role_policy.py`) | Yes (PhD, seniority, experience, country, security roles). Single source of truth: the API and sync audit now call it. `evaluate_eligibility()` returns eligible / eligible_needs_review / excluded / source_unverified with reasons and flags | Yes — `test_eligibility_decision` 3/3, `test_target_sync_audit` 11/11, `test_job_filter_policy` 6/6 (full offline suite earlier in the session: 34/35 runnable passed, the 1 failure was the missing Frontend Developer title, then fixed; the 11 role/eligibility/API/matching tests were re-run after the fix and all passed; the whole suite was not re-run end to end after that last fix) | Compared against the 331 stored jobs (see Session 3) | Salary/compensation helpers and location-matching helpers still live in `app/api/main.py`; `evaluate_eligibility` is not yet exposed through an API field |
| Collectors (Google, Amazon, Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle HCM) | Yes | Mock/unit tests pass | Only Google, NVIDIA (Workday), CRED & Meesho (Lever) marked active; Coinbase/KnowBe4 in `job_sources.json` | Pagination/retry/backoff/health states not uniformly verified; no source-health table |
| 50-company registry (`data/target_companies.json`) | **30 companies only** | `test_target_company_integrations` 11/11 | See below | 20 more companies not chosen; 19 of 30 have no connector |
| Database (`app/db`, SQLite) | Companies + Jobs via SQLAlchemy; tracker/email tables via raw `sqlite3`. DB path now resolved in one place (`resolve_database_path()`, env `JOBPILOT_DATABASE_PATH`) | `test_database`, `test_dedup_constraint` now use a temp DB and pass repeatedly (session 2) | Live DB: 3 companies, 331 jobs | No migrations, no job versions/source-sync history; `main.py` still builds its own second SQLAlchemy engine; `test_structured_job_matching` reads the live DB path directly (read-only) |
| Matching (`job_matcher`, `jd_analyzer`, cache) | Yes | Pass (`test_job_matching`, `test_structured_job_matching`, `test_job_match_api`, `test_job_match_cache`, `test_jd_analyzer`) | Not verified on real jobs here | Weights not configurable via UI/config; skill-gap intelligence missing |
| Local AI (Ollama) | `ollama_client`, `jd_insights` | Ollama-dependent tests **not run** (skipped) | Not verified this session | Provider abstraction, caching/prompt versioning to confirm |
| Resume Studio | Parser, evidence store/selector, builder, PDF, evaluator | Synthetic tests pass; real-resume tests **not run** (sandbox excluded personal resume) | Not verified | No Resume Studio UI beyond generate/download; no DOCX preview/version history UI |
| Application tracker (`app/applications/tracker.py`) | Yes (14 routes) | `test_application_tracker` passes | 1 application in live DB | — |
| Gmail integration | Read-only scope only (`gmail.readonly`) | `test_email_integration`, `test_submission_gmail_lifecycle` pass | 100 messages scanned, 12 events in live DB (not re-verified) | Strict-match rules to re-audit; no live sync run this session |
| Chrome extension (`browser_extension/jobpilot-form-assistant`) | MV3 popup + scripting, localhost only | Root-level `.mjs` test **not run** | Not verified in a browser | Single `popup.js` (895 lines); no portal adapters |
| Frontend (`frontend/`) | One 4,025-line `App.tsx` + 1 component | Build/lint **not run** this session | Not verified | No routing/pages for most planned navigation items; no design system |
| API security | Local-only, CORS allow-list | — | — | No authentication; fine for localhost, blocker for any hosted use |

## 30-company registry state (from `data/target_companies.json`)
- **Active + verified (4):** Google (google_careers), NVIDIA (workday), CRED (lever), Meesho (lever).
- **Configured, awaiting live validation (7):** Amazon, Uber (oracle_hcm), Adobe & BrowserStack (workday), Razorpay & Groww (greenhouse), Freshworks (smartrecruiters).
- **No connector yet (19):** 13 `pending_ats_discovery` (Microsoft, Meta, Salesforce, LinkedIn, Intuit, ServiceNow, Rubrik, Confluent, Flipkart, Zomato, Zepto, Dream11, Postman) and 6 `official_career_page_only` (Atlassian, Apple, Databricks, PhonePe, Swiggy, Zoho).
- The registry uses a different status vocabulary from the target one (discovered/configured/awaiting_validation/verified/active/…); migration needed.
- The live DB only contains Coinbase (225), KnowBe4 (68), Google (38) — the multi-company sync output exists only as audit CSVs at the repo root.

## Baseline test run (sandbox copy, before changes)
Run with `venv\Scripts\python.exe -m scripts.<name>`; network/Ollama tests skipped.

- **Passed (28):** amazon_detail_fetch_policy, api, application_tracker, candidate_profile, candidate_profile_matching, candidate_profile_vault, discovery_directory_api, email_integration, google_collector, google_detail_fetch_concurrency, google_job_details, google_pagination, google_pagination_details, google_query_tiers, google_search_concurrency, jd_analyzer, job_match_api, job_match_cache, job_matching, job_normalizer, local_stack_verifier, multi_source_collectors, resume_builder, resume_evaluator, structured_job_matching, submission_gmail_lifecycle, target_company_integrations, workday_detail_enrichment.
- **Failed before changes (9):**
  - Real regressions (4): `test_target_sync_audit` (7 of 11), `test_job_filter_policy`, `test_security_role_coverage`, `test_google_composite_performance`.
  - Test-isolation (2): `test_database`, `test_dedup_constraint` — insert "Google" into the live DB path; fail with `UNIQUE constraint failed: companies.name` once the DB is populated.
  - Sandbox artefacts (3, not real failures): `test_resume_evidence_selector`, `test_resume_evidence_store`, `test_resume_parser` need the personal resume under `data/master_resume/`, which the sandbox deliberately excluded.
- **Skipped (network/Ollama):** environment, google_careers, greenhouse, greenhouse_connection, ollama, ollama_jd_analysis, requests.

## Changes made in session 1
1. `app/services/target_role_policy.py` — commit `f09230e` had overwritten the policy with an older snapshot. Restored from `f09230e~1`: PhD exclusion (title and minimum-qualifications), Amazon-style and "N years in a … role" experience parsing, ISO-alpha-2 country codes and extended country list, "minimum requirements/required experience" section headers, and **Engineer III is no longer excluded by title number** (rule 8). Kept the new cloud/threat-detection/security-automation title additions from that commit.
2. `app/api/main.py` — `TARGET_SOFTWARE_ROLE_PATTERN` had the new security titles appended **outside** the regex group, leaving a trailing `|` (an empty alternative that matches every title). Moved them inside the group. Also changed `commission` → `commissions?` in `NON_SOFTWARE_ROLE_PATTERN`.
3. `scripts/test_security_role_coverage.py` — added a regression guard so unrelated titles ("Head Chef", "Warehouse Operator", "Senior Commissions Analyst") can never match the API feed filter again.

### After changes (run in the real project; these tests do not write to the DB)
Passed: `test_security_role_coverage`, `test_job_filter_policy` 6/6, `test_target_sync_audit` 11/11, `test_google_composite_performance`, `test_workday_detail_enrichment`, `test_target_company_integrations` 11/11, `test_structured_job_matching` 5/5, `test_job_match_api` 3/3.
**Not re-run after the change:** the rest of the suite, frontend build/lint, extension test, anything needing Ollama, network, Gmail or the real resume.

## Session 2 (10 Nov): test isolation
- `app/db/database.py` now exposes `resolve_database_path()` honouring `JOBPILOT_DATABASE_PATH`; `app/api/main.py`, `app/applications/tracker.py` and `app/email/gmail_integration.py` delegate to it instead of keeping three copies. Default path is unchanged.
- Found that `scripts/test_database.py` and `scripts/test_dedup_constraint.py` inserted rows straight into the **live** `jobpilot.db`. Rewrote both to use a temp DB with real assertions. Verified: ran each twice in the real project; SHA-256 of `jobpilot.db` identical before and after.
- Full offline suite (sandbox copy, `JOBPILOT_DATABASE_PATH` pointed at the copy): **34 passed, 0 failed, 10 skipped** (7 need network/Ollama, 3 need the personal resume). Skipped tests were not run.
- Scheduled-task/SESSION_RULES.md referenced a non-existent `JOBPILOT_DB_PATH`; corrected to `JOBPILOT_DATABASE_PATH`.

## Session 3 (11 Nov): role-policy centralisation
- `app/api/main.py` no longer carries its own seniority/intern/PhD/role-family/experience regexes; `_is_target_software_role`, `_is_early_career_suitable`, `_extract_required_experience_years` and `_requires_phd` are thin wrappers over `target_role_policy` (new public helpers: `matches_software_role_family`, `early_career_title_exclusion`, `requires_phd`, `is_non_software_title`).
- New `evaluate_eligibility()` / `EligibilityDecision`. `scripts/sync_target_companies.py::_make_audit_row` now uses it; the CSV keeps its old vocabulary (excluded -> `filtered`, unverified source -> `eligible_needs_review`).
- **Bug found and fixed:** the experience extractor read "4 year degree in CS or equivalent experience" as 4 years of experience, which would wrongly exclude entry-level jobs. Degree-length nouns are now ignored (regression test in `scripts/test_eligibility_decision.py`).
- **Behaviour change, measured on the 331 stored jobs (read-only sandbox copy), API vs previous API logic:** early-career-suitable 85 -> 63. The old API extractor found no experience requirement in most descriptions (min-years found: policy finds far more), so e.g. "Software Engineer ... 3 years" used to pass. 24 jobs went suitable -> not suitable (all because of a stated requirement above 2 years or an "IV"-level title; I read the list); 2 non-software Account Executive jobs went the other way because "1-3 years" now uses the lower bound (1) instead of the maximum (3) and they are outside the software role family anyway. Role-family: 2 more jobs pass (Product Security Engineer, Data Application Engineer), matching the brief.
- The central role-family list was also missing "developer" variants the API had (Frontend/Backend/Full-Stack Developer, Test Automation Engineer, "Back End" spelling); added and covered by a test. Role-family: nothing that passed before is lost.
- Ranges now use the **lower bound** everywhere (e.g. "1-3 years" -> 1), consistent with "an explicitly stated two-year minimum can qualify".

## Known risks / debt
- Role-filter logic exists in two places (`target_role_policy.py` and `app/api/main.py`); that duplication is what allowed this regression. Centralise next.
- No schema migrations; tracker and Gmail tables are managed with raw SQL separately from SQLAlchemy models.
- Workspace clutter: `*.bak` files (`app/api/main.py.*`, `frontend/src/App.tsx.*`, `data/target_companies.json.before_discovery.bak`), three backup `.db` files, 10 `target_sync_*` CSV/TXT files at the repo root, empty `_jobpilot_extension_submission_patch/`, stray root `scripts_test_extension_submission_confirmation.mjs`. Not touched this session (user's call before deleting).
- API has no authentication.
- Nothing about live Gmail, Ollama, employer portals or the Chrome extension was verified in a real session.

## Needs manual testing / live credentials
Gmail sync with the real account, Ollama inference, extension on a real employer form, each ATS source against the live endpoint.
