# JobPilot — Project Status

_Last updated: 2026-11-17. Based on code inspection, automated tests and the live checks listed below. No percentage estimates._

## Verdict

JobPilot is a working **personal tool**: discovery from 19 validated company sources, eligibility and explainable matching, recommendations, evidence-based documents, a tracker with history, an extension, read-only Gmail matching, analytics, contacts and interview prep. It is **not** a finished or production-ready product: several parts have only been tested with mocks or synthetic data (see "Needs your verification"), the registry is 40 companies not 50, and it is single-user with no accounts.

Latest full offline regression (`python -m scripts.run_offline_tests`, temporary database copy): **53 passed, 0 failed, 10 skipped** (51 Python scripts and 2 extension test files). The skipped ones need live career sites, a running Ollama or the personal resume and were **not run** in that pass. Frontend `tsc`, lint and build are clean. The real database was not touched by testing.

## Safety rules for this repo
- Never open or print `.env`, `credentials/`, `tokens/`, `frontend/.env.local` or the Gmail token files.
- Tests run on temporary databases (`JOBPILOT_DATABASE_PATH`); `run_offline_tests` copies your database first.
- Live source sync only touches sources that are `active` and verified. Application submission, email and recruiter messages stay human-controlled.

## Module matrix

"Real-world verified" means checked against the real system (live site, real model, real browser), not a mock.

| Module | Implemented | Automated tests | Real-world verified | Missing / limits |
|---|---|---|---|---|
| Source registry and health | 40 companies; 19 active, 8 awaiting validation, 13 discovered; explicit states; fetch history; coverage page | `test_source_health`, `test_target_company_integrations` | Live read-only dry runs on 14-15 Nov for the 18 sources promoted since | 10 companies short of 50; 13 have no connector (Microsoft's official API found, connector not written); Uber and four name-only-evidence sources need your manual ownership check; pagination status not reported by connectors; no retry/backoff in collectors |
| Collectors and sync | Needs-review jobs are stored and held in a "Needs your review" tab (Accept / Dismiss / Restore; your decision survives later syncs); a "Check if still open" button re-reads one job's source; Greenhouse, Lever, Ashby, SmartRecruiters (with details), Workday, Oracle HCM, Amazon, Atlassian, Google; dedup, versions, change and removal detection, FULL/FAST, concurrency | `test_collector_validation_fixes`, `test_sync_modes`, `test_job_versions`, `test_multi_source_collectors`, `test_job_review`, `test_job_status` | Yes for the sources above (found and fixed Amazon, Uber and Workday pagination bugs that mocks had hidden). Never run as a live write to your real database from here | NVIDIA predates the Workday pagination fix: re-run it. Salesforce not dry-run (global board) |
| Eligibility policy | One rule set (role, seniority, PhD, experience, country); states with reasons | `test_eligibility_decision`, `test_job_filter_policy`, `test_target_sync_audit` | Compared on 331 stored jobs | Rules are strict, so most boards yield few candidates |
| Matching and recommendations | Explainable score, configurable weights, eligibility cap, mismatch categories, comparison, next actions, skill gaps | `test_match_explainability`, `test_opportunities`, `test_structured_job_matching` | Recommendations on your real stored jobs (6 candidates) | Weights not validated against outcomes; deadline and competition not modelled |
| Local AI | Provider layer, validated fit analysis, cache, retries, off switch | `test_ai_layer` (fake provider) | **Yes**: one real fit analysis on your `gemma3:4b` (rules overrode the model, cache worked) | First call took 3m43s on CPU; set `JOBPILOT_OLLAMA_TIMEOUT=400`. No mock AI interviewer |
| Resume Studio | Reads the job's required and preferred skills automatically; you tick each missing skill to include it (this resume only, labelled "added by you"); versions per job, tailoring report, fail-closed fabrication check, DOCX/PDF | `test_resume_versions` (4 tests), `test_resume_builder`, `test_resume_evaluator` | Not with your real resume (synthetic evidence only); the new choices panel was **not seen in a browser** | Real-resume tests not run in the last pass |
| Cover letters and answers | Verified-facts template, versions, exports; answer library with confirmations | `test_cover_letters_answers` | Not with your real profile | No AI polishing (deliberate); extension does not use approved answers |
| Tracker and history | Readiness checklist, applied-only-on-confirmation, history by trigger, follow-ups | `test_application_lifecycle`, `test_application_tracker` | Existing live data predates history (backfilled) | No archive; extra statuses from the brief not added; no history view in the UI |
| Gmail | Read-only; strict matching (applied, company, role, date); closed postings still match; approval queue; suggested follow-ups | `test_email_integration` (20 tests, mocked mail), `test_submission_gmail_lifecycle` | **Not verified live** | Needs your account; full bodies are never stored (tested) |
| Analytics, contacts, interview prep | Funnel with small-sample rule, contact book (draft-only outreach), plan with progress | `test_insights_crm_prep` | Not with real activity | Contacts and prep have API only (no screen) |
| Browser extension | Pure matcher module (parity-checked against the old rules on 3,744 cases), portal detection, never submits | `test_extension_field_matcher.mjs`, confirmation test | **Not verified on a real form or in Chrome** | Embedded cross-origin frames likely unreadable; no token support |
| Frontend | Modular; Overview, Discover, Recommended, Applications, Cover letters & answers, Resume studio, Company coverage, Insights, Email | `tsc`, lint, build | Overview, Discover, Applications, Resume, Email and Coverage rendered in a browser on 14-15 Nov with no console errors. **Recommended, Cover letters & answers, Resume versions panel and Insights were not seen in a browser** (pane hidden) | No URL routing; no design-token pass |
| Security and operations | Optional API token, CORS config, backup/restore, `run_offline_tests`, docs | `test_security_and_backup` | Backup/restore tested on temp files | Token not for extension or download links; no accounts; no monitoring |
| Deployment | Dockerfiles, compose, nginx, `.env.example` | compose file syntax-checked | **Images never built** (no Docker daemon) | No migrations framework; Postgres untried |

## Needs your verification (cannot be done from here)

1. Click through **Recommended, Cover letters & answers, Resume studio (versions), Insights** in a browser.
2. Load the extension in Chrome and try it on a real Greenhouse, Lever and Workday form.
3. Connect Gmail and run a real sync.
4. Run `scripts.sync_target_companies --mode full` against your real database (back up first) and re-run NVIDIA.
5. Confirm ownership for Uber, Zscaler, GitLab, Twilio, InMobi, ServiceNow and Swiggy before setting them verified.
6. `docker compose up --build` once and check the backend is healthy.
7. Try the resume, cover-letter and answer features with your real resume evidence.

## Session log (the 26-30 Nov work first, then earlier sessions in order)

## Session 10 (17 Nov): work planned for 26-30 Nov
- **Extension (26 Nov):** the matching rules moved into `field_matcher.js` (pure, no DOM or network); `popup.js` shrank from 895 to 773 lines and injects the matcher first. Behaviour parity was proven on 3,744 label/type/element combinations (0 differences) before the change. Portal detection (Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle) reports which portal was seen; unknown portals still fill only clearly labelled fields and say so. New `scripts/test_extension_field_matcher.mjs` (8 tests, including static checks that nothing can click, submit or upload and that sensitive questions are never matched). **Not tried in Chrome.**
- **Gmail (27 Nov):** audit with mocked mail. Fixed: a job that had been taken down no longer stops replies matching its submitted application (this mattered because removal detection now marks closed jobs inactive); a message whose date cannot be determined never matches; RFC 2822 `Date` headers are understood; approval now writes a suggested next action and follow-up date (only when you had none; nothing is sent). 5 new tests (20 total, all passing). **Not run against a live account.**
- **Analytics, contacts, interview prep (28 Nov):** `GET /api/analytics/funnel` (rates hidden below 10 applications), contact book with draft-only outreach (marking as sent only records that you sent it), `POST /api/applications/{id}/interview-prep` with progress tracking (assessment stage skips design rounds). Insights screen added. 3 tests. Contacts and prep have no screen yet. The AI mock interviewer was not built.
- **Security and operations (29 Nov):** optional API token (`JOBPILOT_API_TOKEN`, constant-time check, registered inside CORS so a rejected browser call still shows a 401), configurable CORS origins, frontend token support via `VITE_API_TOKEN`, `scripts/backup_database.py` (online backup, integrity-checked, retention, restore with a safety copy), Dockerfiles, compose, nginx config, `.dockerignore`, `.env.example`. 4 tests. Images unbuilt.
- **Docs and regression (30 Nov):** rewritten README; `docs/` with installation, configuration, architecture, deployment, troubleshooting, security checklist, release checklist, cleanup proposal and a generated API reference (88 endpoints); `scripts/run_offline_tests.py` (runs every offline test against a temporary database copy) and `scripts/generate_api_docs.py`.

## Session 11 (17 Nov): sandbox run of the whole app on a copy of your database
Your real database was never touched. Findings, all from running the real thing:
- **Why only Google and Greenhouse jobs showed:** your real database only holds Coinbase, KnowBe4 and Google, because the 19 validated sources had never been synced into it. Two more causes were found and fixed: (1) jobs with no stated minimum years of experience (most of Amazon's entry-level roles) were silently dropped by the sync, so they are now stored and held in a **Needs your review** tab (Accept / Dismiss / Restore; your decision survives later syncs); (2) the default "India" filter only matched the word India, so Amazon ("IN, TS, Hyderabad") and CRED ("bengaluru") were stored but invisible. It now uses the same India rule as the sync.
- **Bug found only by the live run:** on a database from before the new tables, the sync failed for 10 of 19 sources with "database is locked" (a table was created in the middle of a write). The tables are now created before any write, with a regression test. Mocks had hidden this.
- **Live sandbox sync result (19 active sources, 0 failed):** 5,096 live jobs read; 81 pass role and location; 14 clean plus 67 held for review. After the fix, the default list shows Google 7, Amazon 4, CRED 2, Rubrik 1 and the review tab holds 65 (Amazon 53, Stripe 4, Rubrik 3, MongoDB 2, and one each for Google, Elastic, Atlassian). The other 9 sources (Adobe, NVIDIA, Razorpay, Meesho, Groww, Freshworks, BrowserStack, Okta, Druva) had live jobs but none passed the India, software, early-career rules.
- **Closed jobs:** the full sync marked 31 stored Google jobs as closed (no longer listed). Coinbase and KnowBe4 jobs are not in the registry, so they are never re-checked.
- **Browser check (DOM, pane hidden so no screenshots):** the three job tabs; Accept moved a job from review (65 to 64) into the main list (15 to 16); Tailor resume auto-filled required and preferred skills and offered the three unverified ones as tick boxes; "Check if still open" showed its message. A live check via the API returned "open" for a CRED and a Rubrik job.
- **Known gaps:** a few held jobs are US-remote ("Remote US") because the policy treats a plain Remote label as unverified; dismiss them. Amazon's 53 held jobs are mostly "years not stated". Recommended, Cover letters, Resume versions and Insights screens are still not seen in a browser. Gmail still unverified live by me.
- 52 offline tests pass, tsc and lint clean.

## Session 12 (18 Nov): next steps after the sandbox run
- **Retry and backoff for every collector:** requests now retry temporary failures (429 and 5xx) three times with growing waits; a 404 or 403 still fails at once. Workday also retries a 200 answer with an unreadable body (NVIDIA returned one under concurrency 3 in a live run). 4 tests with a local fake server. Not a guarantee against a site that blocks us.
- **Remote jobs for a foreign region** ("Remote US", "Remote - USA", "Remote (UK)", "Remote, EMEA") are now excluded instead of held for review; a plain "Remote" is still held, and a location naming India stays eligible. In the live sandbox sync Toast went from 1 held job to 0.
- **Known gap:** a US job that lists only states or a city with a remote label (for example Databricks, "Washington, D.C.; Remote") still reaches the review tab; dismiss it. Recognising every US state was left out on purpose to avoid wrongly excluding Indian cities.
- 53 offline tests pass.

## Registry state as of 14-15 Nov (historical; current counts are in the matrix above)
- **Active + verified (18, updated 15 Nov):** Google, NVIDIA, CRED, Meesho, Amazon, Razorpay, Groww, BrowserStack (14 Nov), Adobe, Atlassian, Databricks, Rubrik, Okta, MongoDB, Toast, Stripe, Druva, Elastic (15 Nov).
- **Awaiting validation (9):** Uber (ownership unconfirmed), Salesforce (not dry-run), ServiceNow / Swiggy / Freshworks (no descriptions), Zscaler / GitLab / Twilio / InMobi (board-name-only evidence).
- **Discovered, no connector (13):** see Session 7.
- NVIDIA's earlier verification predates the Workday pagination fix: it was collecting only 40 of ~2,000 postings. Re-run it after the next network window.
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

## Session 4 (12 Nov): frontend and extension baseline
- Frontend: build passed first time; lint failed with 1 error (`@typescript-eslint/no-explicit-any`, `ApplicationPreparationPanel.tsx` line 155). Replaced with a typed `{ detail?: unknown }` payload, no behaviour change. Build and lint now both clean.
- Extension: syntax, manifest and the confirmation test all pass; no change needed.
- Browser smoke test used a copy of the DB, servers were stopped afterwards, real `jobpilot.db` untouched. Backend code was not changed today, so the backend suite was not re-run.

## Session 5 (13 Nov): source health model
- New table `source_health` (SQLAlchemy model `SourceHealth`, created idempotently with `checkfirst`, no other table touched) and `app/services/source_health.py`.
- States: discovered, configured, awaiting_validation, verified, active, temporarily_unavailable, failed, deprecated. `registry_state()` maps the registry vocabulary: `active`+verified+connector -> active; `configured_needs_live_validation` -> awaiting_validation; `pending_ats_discovery` / `official_career_page_only` -> discovered. `status: active` without the verified flag or connector settings is **not** trusted (awaiting_validation). Only `active` may enter automatic sync.
- Runtime history can only **downgrade** a trusted source (1-2 consecutive failures -> temporarily_unavailable, 3+ -> failed); nothing is ever promoted by a successful fetch, promotion stays a manual registry edit.
- `scripts/sync_target_companies.py` records per company: raw / unique / eligible / review counts, jobs with a description, detail-enrichment attempted/succeeded (only where the connector reports it, e.g. Workday; otherwise NULL, not 0), last success / failure, error, consecutive failures. One failing company does not stop the rest. Live sync always records; a **dry run records nothing unless `--record-health` is passed**.
- `GET /api/sources/health` (read-only; does not create the table) returns every registry company with state, links and history. On the real registry with no history: 30 total, 19 discovered, 7 awaiting_validation, 4 active, 30 never fetched.
- Full offline suite (sandbox copy): **36 passed, 0 failed, 10 skipped** (7 need network/Ollama, 3 need the personal resume; skipped = not run).
- Tests: `scripts/test_source_health.py` 6/6 (state mapping, real-registry sanity, downgrade rules, history/recovery, API read-only behaviour, sync + dry-run behaviour). Real `jobpilot.db` hash unchanged during testing.
- Not done / limits: **pagination status is stored but no connector reports it yet** (always `not_reported`); unique-job count uses external_id/url within one fetch, not cross-source deduplication (planned for 18 Nov); `load_registry()` in the sync script still insists on exactly 30 companies and must be relaxed when the registry grows; no UI yet (16 Nov); no real-network fetch was run, so no health rows exist yet.

## Session 6 (14 Nov): live validation of the 7 configured sources
Read-only dry runs against the real public endpoints (job tables never written; health rows went to a throwaway DB copy; real `jobpilot.db` hash identical before and after). Official-page evidence: identifiers for Razorpay, Freshworks, BrowserStack and Adobe were found on each company's own careers page; Groww's board returns the name "Groww" and is referenced on groww.in/careers.

| Source | Result (live) | Decision |
|---|---|---|
| Razorpay (greenhouse) | 26 jobs, 26/26 descriptions, 0 role-eligible now | promoted to active |
| Groww (greenhouse) | 9 jobs, 9/9 descriptions, 0 role-eligible now | promoted to active |
| BrowserStack (workday wd3) | 34 jobs, 34/34 detail fetched, 0 role-eligible now | promoted to active |
| Amazon (amazon_jobs) | 364 India jobs = server total, all with descriptions, **65 role-eligible** (was 9) | promoted to active |
| Uber (oracle_hcm) | 32 India jobs, 32/32 descriptions, 0 role-eligible now | **not promoted**: could not confirm the Oracle site belongs to Uber (uber.com returned HTTP 406 to an automated check). Manual step: confirm an Apply link lands on `iaziqy.fa.ocs.oraclecloud.com` / `UberCareers`, then set `verified` |
| Adobe (workday wd5) | HTTP 521 | **not promoted, not failed**: NVIDIA's wd5 tenant returned 521 at the same time, wd3 worked: a Workday wd5 cluster outage. Re-run later |
| Freshworks (smartrecruiters) | 32 jobs, all India, **0/32 descriptions** | **not promoted**: filters can't run without descriptions; needs posting-detail enrichment |

Full offline suite after these changes (sandbox copy): **37 passed, 0 failed, 10 skipped** (7 need network/Ollama, 3 need the personal resume; skipped = not run). The live dry runs are not part of the automated suite.

Bugs found that mocked tests had hidden (fixed, with tests in `scripts/test_collector_validation_fixes.py`):
- **Amazon:** the collector sent `country[]=IND`, which amazon.jobs silently ignores (2,637 worldwide hits), so it spent its 400-job cap on mostly foreign roles and only saw 40 India jobs. The working parameter is `normalized_country_code[]=IND` (364 hits). The `industry_experience` band filter is also unreliable (one band returned every job), so the default is now a single unfiltered India pass and experience is judged from the description.
- **Uber/Oracle HCM:** the finder's `workLocationCountryCode` is ignored (818 jobs, 777 outside India). The country is now filtered client-side on `PrimaryLocationCountry` (rows with no country field are kept, not discarded). The list payload has no descriptions, so an opt-in detail fetch (`recruitingCEJobRequisitionDetails`) was added, bounded by `max_detail_fetch`, one request per job, failures tolerated; enabled for Uber in the registry.
- Test expectation changed (explained in the test): `test_target_company_integrations` had pinned `country[]` and the old "configured" statuses; both reflected the unvalidated assumptions.
- Side finding: the entire Workday **wd5** cluster, including NVIDIA (an active source), was unreachable on 14 Nov; NVIDIA's health will show `temporarily_unavailable` if a sync is recorded now.
- Still true: 0 candidates for five sources means no current 0-2-year software roles passed the policy, not that the connectors are broken (reasons are in the audit CSVs). The audit CSVs and logs were written to a scratch folder, not the repo. Collectors still have no retry/backoff (planned work).

## Session 7 (15 Nov): mapping the unmapped companies and growing the registry
Method: instead of grepping script-rendered careers pages (which gave nothing), I probed the public board APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workday CXS) with company-name slugs and accepted a mapping only with ownership evidence. Strong evidence = every job URL on the company's own domain (only the board owner can configure that), an official feed on the company's own domain, or a link on the official careers page. Board-name match alone is *not* enough to promote.

**Bug found by live testing and fixed:** the Workday collector stopped after 2 pages because Workday reports `total` only on the first page (Adobe: 246, then 0, 0). Every Workday source was truncated to 40 jobs, including NVIDIA (active; the board reports 2,000). Fixed by remembering the first positive total, with a test. Adobe went from 40 to all 246 postings.

**New connector:** `atlassian_careers` (`app/collectors/atlassian_careers.py`) reads Atlassian's own careers JSON, one request, descriptions included, duplicate ids removed, no invented posting date.

Registry changes (all in `data/target_companies.json`, each entry has the evidence in its `notes`):
- **Promoted to active (10, dry-run evidence in notes):** Adobe (now complete), Atlassian, Databricks, Rubrik, Okta, MongoDB, Toast, Stripe, Druva, Elastic. Together with the 8 active before: **18 active**.
- **Added but held (awaiting validation) because ownership is only a board-name match:** Zscaler, GitLab, Twilio, InMobi. Dry runs were clean; confirm each company's Apply link lands on its Greenhouse board, then set `verified`.
- **Mapped but held, no descriptions from SmartRecruiters' list endpoint:** ServiceNow, Swiggy (same limitation as Freshworks; needs posting-detail enrichment, planned 19 Nov).
- **Mapped but not dry-run:** Salesforce (Workday CXS answers, 1,609 postings; a full dry run would make one detail request per posting, so wait for detail-fetch limiting). Uber still needs the manual ownership check from 14 Nov.
- **Still no connector (13):** Microsoft (official `apply.careers.microsoft.com/api/pcsx/search` JSON works; connector not written), Meta, Apple, LinkedIn (a tiny unrelated-looking Lever site was rejected), Intuit, Confluent, Flipkart, PhonePe, Zomato (a 4-job Lever site rejected), Zepto, Dream11, Postman, Zoho. No public board found by direct probe.
- **Companies rejected for the extra list:** probed and dropped for having no India engineering roles: Cloudflare, Pinterest, Airbnb (2), Datadog (1), Lyft, DoorDash, Dropbox, Box, Asana, Reddit, Robinhood, Duolingo, Brex, Anthropic, Vercel and others; Indian startups probed with no public board found: Juspay, Chargebee, CleverTap, Cashfree, ShareChat, Lenskart, Sprinklr, Innovaccer and others. The first-batch counts are in the notes only for the ones added.
- `load_registry()` in the sync script and the discovery script no longer insist on exactly 30; they require at least the original 30, unique ids and unique names (tests added).

Full offline suite after these changes (sandbox copy): **37 passed, 0 failed, 10 skipped** (7 need network/Ollama, 3 need the personal resume; skipped = not run). The live dry runs are not part of the automated suite.

Live dry-run summary (read-only; job tables untouched; real `jobpilot.db` hash unchanged): candidates found now — Stripe 4, GitLab 6, Rubrik 3, InMobi 3, MongoDB 2, Twilio 2, Databricks/Atlassian/Toast/Elastic/Zscaler 1 each, Okta/Druva 0. Candidates still need human review (audit status `eligible_needs_review`) because a posting's experience/location is checked by rules, not by a person.

Limits to remember: the 0-2 year + India + software policy is strict, so most boards yield few candidates; a mapped source is not a guarantee of suitable jobs. Pagination status is still not reported by connectors. Collectors still have no retry/backoff.

## Session 8 (15 Nov): work planned for 16-20 Nov
**Frontend (16-17 Nov)**
- `frontend/src/App.tsx` (4,025 lines) was split mechanically by a script into `config.ts`, `types.ts`, `nav.ts`, `lib.tsx` (helpers), `components.tsx` (shared components), `views/{Overview,Jobs,Applications,Resume,EmailIntelligence}View.tsx` and a 1,028-line `App.tsx` that keeps state and routing. No logic was edited. `tsc`, ESLint and the production build are clean; in the in-app browser all six screens render real content with no console errors.
- New **Company coverage** page (`views/CoverageView.tsx`, nav entry works) backed by `GET /api/sources/health`: state badges, connector, last success, raw/unique, eligible/review, descriptions, detail fetch, last problem, state filter and search, loading/error/empty states. Verified against real recorded dry-run data (e.g. Amazon 364/364, Adobe 246/246).
- Not done from the 17 Nov brief: client-side routing (screens are still one `screen` state, no URLs), a design-token pass using the named design resources, and splitting the remaining 1,028-line `App.tsx` state into hooks.

**Sync data quality (18-19 Nov)**
- New `job_versions` table (snapshot per change: baseline / created / updated / reactivated / removed, with changed fields and a content hash). `JobRepository.upsert_job_detailed()` reports created / updated / unchanged / reactivated; whitespace-only edits are not changes; jobs stored before versioning get a baseline. `upsert_job()` still works.
- Removal detection (`mark_missing_inactive`) runs only after a complete FULL fetch and is skipped when the fetch looks partial (fewer than half of the stored active jobs); FAST mode and `--no-removal-detection` never remove.
- `sync_target_companies --mode full|fast`: FAST reuses stored descriptions for known jobs (Workday, Oracle, SmartRecruiters) and trims Google's low-yield queries. Benchmark (`python -m scripts.benchmark_sync_modes`, mocked): second sync of 200 known jobs with 10 edited and 5 new needs 205 detail requests in FULL, 5 in FAST; FAST finds all 5 new jobs but 0/10 edits. `--concurrency 1-8` fetches companies in parallel while database writes stay sequential; one failing company does not stop the others.
- SmartRecruiters detail enrichment (the live detail shape is `jobAd.sections` as a dictionary; the old parser expected a list): ServiceNow 80/80, Swiggy 191/191, Freshworks 32/32 descriptions fetched in live read-only dry runs. Freshworks promoted to active; ServiceNow and Swiggy stay awaiting validation (ownership evidence is only the SmartRecruiters company name).
- Monitoring: `GET /api/sync/summary?days=N` and `scripts/run_scheduled_sync.py` (sync, print and save a summary under `data/sync_reports/`, with a Windows Task Scheduler command in its docstring). Summaries are computed from the version history, so an event is reported once; with no history yet it says so instead of showing zeros.
- Not done: a separate shared location-normalisation module (the central policy already holds the India/remote rules), a per-job "description completeness" field (the per-source counts exist in `source_health`), and a user-facing page for the sync summary.

**Matching (20 Nov)**
- `data/match_weights.json` + `app/services/match_weights.py`: six component weights (role 25, seniority 20, experience 20, skills 20, education 10, location 5), validated (all components present, non-negative numbers, total 100) and applied by rescaling each component; they are part of the match-cache key and the cache version is bumped, so editing the file re-scores jobs. A corrupt file raises instead of silently using defaults (the loader cached on mtime at first, which could serve a stale file after two quick rewrites; fixed with nanosecond mtime + size).
- Deterministic eligibility is authoritative: a role/experience/PhD exclusion from the central policy caps the match score at 35 however many skills overlap, with the reason added to the concerns. Location is still scored separately and is not capped.
- Match output now includes `mismatches` (mandatory requirement, preferred skill missing, experience, location, seniority), `weights` and `eligibility`; `GET /api/jobs/compare?ids=a,b[,c,d]` returns scores, blockers, a skill matrix and skills missing everywhere.
- Limits: the brief's example weights (technical skills 30, responsibilities 20, framework 15, ...) do not map to the matcher's six components, so I kept its components; weights were not "validated against real examples" beyond unit tests; the comparison has no UI yet; the analyzer does not extract every skill (for example a standalone "Go"), which limits the skill matrix.

Full offline suite after all of the above (sandbox copy): **41 passed, 0 failed, 10 skipped** (7 need network/Ollama, 3 need the personal resume; skipped = not run). Frontend `tsc`, lint and build clean; extension checks pass. Live dry runs and the browser smoke test are separate from the automated suite.

**Registry:** 40 companies, **19 active**, 8 awaiting validation, 13 discovered. Real `jobpilot.db` hash unchanged throughout; all live work used throwaway copies.

## Session 9 (16 Nov): work planned for 21-25 Nov
**AI layer (21 Nov)** - `app/ai/providers.py`, `runner.py`, `fit_analysis.py`
- Provider interface; default is local Ollama (`gemma3:4b`); `JOBPILOT_AI_PROVIDER=none` turns AI off; no external provider exists unless one is explicitly registered **and** selected. Selection errors degrade to the rule-based result.
- `run_structured`: retries transient failures with exponential backoff (3 attempts), one retry on unusable output, a missing model is not retried; results cached in `ai_cache` keyed on task + prompt version + provider + model + inputs (only the validated result is stored); logging records metadata only (task, version, model, sizes, duration), never prompt or answer text.
- `POST /api/jobs/{id}/ai-fit`: candidate-vs-job analysis (matched/missing skills, experience fit, strengths, weaknesses, risks, preparation, recommendation). Skills the model lists must be in the job text, matched ones must be in the profile, missing ones must not be; the rule-based score is the score shown; the model can never turn an excluded job into "apply". Works without a model (source `deterministic`). `GET /api/ai/status` reports the selected provider.
- **Verified live against your local Ollama** (`gemma3:4b`, throwaway DB copy): validated output, the rules overriding the model's "apply now" with a note, and a cached second call. The first call took 3m43s on this machine (cold model on CPU), longer than the default 180 s timeout: set `JOBPILOT_OLLAMA_TIMEOUT=400` if you see "unavailable" on the first request.

**Opportunity intelligence (22 Nov)** - `app/services/opportunities.py`, `GET /api/recommendations`, `views/RecommendedView.tsx`
- Next action (apply now / review first / prepare missing skills / skip) from the rule-based match and eligibility only; the opportunity score (fit 60, freshness 15, company priority 15, disclosed pay 10) ranks viable jobs; undisclosed pay is neutral; a skipped job can never rank above a viable one. Application deadlines and competition are not modelled (not collected) and the response says so.
- Skill-gap report counts required skills missing across the jobs worth pursuing, states the sample size (flags samples under 10), and gives learning steps that never tell you to claim a skill you have not used. Sorts: opportunity, score, newest, company, location, experience, salary. UI includes the 2-4 job comparison table. On your real stored jobs: 6 candidates (4 prepare-missing-skills, 2 review-first).

**Resume Studio (23 Nov)** - `app/resume/tailoring_report.py`, `resume_versions` table, `GET /api/resume-versions[/{id}]`, `views/ResumeVersionsPanel.tsx`
- Each generated resume is stored as a version (linked to a job via the optional `job_id`) with a tailoring report: original details reused, keywords aligned, what was selected and ordered, required skills covered / awaiting your review / no evidence, items needing review, and an explicit "master resume unchanged" note. DOCX and PDF downloads work from the list.
- New fail-closed check: every bullet in the finished DOCX must be text of verified evidence; otherwise the files are deleted, nothing is stored and the request returns 422.
- **Bug fixed:** resume filenames had only second-level resolution, so two generations in the same second shared a name and cleaning up a refused one deleted the good one's files. Names now carry a random suffix (regression test added).

**Cover letters and answers (24 Nov)** - `app/applications/{cover_letters,answers,profile_facts}.py`, endpoints under `/api/cover-letters` and `/api/answers`, `views/DocumentsView.tsx`
- Cover letters are a deterministic template (no model, so nothing can be invented) using the job, your profile facts as you wrote them, skills backed by verified evidence, and the first sentence of verified projects; unsupported skills are listed as "not claimed". Edits create new versions; DOCX and PDF export; "save file" lets you attach one to an application.
- Answer library: drafts for salary, notice period, work authorization, technology experience, challenging project, why-company/why-role. Missing facts are reported, never invented; "why this company" is a scaffold with a placeholder; placeholders block approval; salary, work authorization and company-specific answers need an explicit confirmation; editing withdraws an approval; reusable = approved and not tied to a job.
- Not done: AI polishing of letters (deliberately skipped: it would reintroduce the risk of invented claims), and the browser extension does not read the approved answers yet.

**Application workspace (25 Nov)** - `app/applications/tracker.py`
- Verified (tests added, `scripts/test_application_lifecycle.py`): one tracker entry per job, `ready_to_apply` requires the readiness checklist and never sets `applied_at`, only the applied status sets it (and later statuses keep it), removing an entry never deletes the job.
- New: `application_status_history` written by database triggers, so every change is recorded whichever path makes it (tracker API, extension confirmation, email approval); existing applications get a starting row; `GET /api/applications/{id}/history`. Saved cover letters are kept out of the resume dropdown.
- Not done: archive (only delete exists), the extra statuses from the brief (shortlisted, reviewing, on hold; the existing nine are unchanged so the extension and UI keep working), a history view in the Applications UI.

**Verification and limits**
- Backend: the full offline suite ran 45/46 runnable scripts green; the one failure was the filename bug above, now fixed (the nine new/changed test scripts were re-run green in the sandbox). The whole suite was **not** re-run end to end after that last fix. Frontend `tsc`, lint and build are clean.
- **The new screens (Recommended, Cover letters & answers, Resume versions panel) were NOT verified in a browser**: the in-app browser pane was hidden in this session, so clicks had no effect. The endpoints they call were tested.
- 26 Nov (Chrome extension adapters) was not started.

## Known risks / debt
- Role-filter logic exists in two places (`target_role_policy.py` and `app/api/main.py`); that duplication is what allowed this regression. Centralise next.
- No schema migrations; tracker and Gmail tables are managed with raw SQL separately from SQLAlchemy models.
- Workspace clutter: `*.bak` files (`app/api/main.py.*`, `frontend/src/App.tsx.*`, `data/target_companies.json.before_discovery.bak`), three backup `.db` files, 10 `target_sync_*` CSV/TXT files at the repo root, empty `_jobpilot_extension_submission_patch/`, stray root `scripts_test_extension_submission_confirmation.mjs`. Not touched this session (user's call before deleting).
- API has no authentication.
- Nothing about live Gmail, Ollama, employer portals or the Chrome extension was verified in a real session.

## Needs manual testing / live credentials
Gmail sync with the real account, Ollama inference, extension on a real employer form, each ATS source against the live endpoint.
