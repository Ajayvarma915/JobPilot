# JobPilot — Roadmap

Ordered by impact. Core discovery and application pipeline first; advanced intelligence only after the data underneath is trustworthy. See `PROJECT_STATUS.md` for the current evidence.

## Phase 0 — Audit (done, session 1)
- Repository mapped, baseline recorded, role-filter regressions repaired and covered by a new guard test.

## Phase 1 — Core discovery (next)
1. ~~**Centralise the role/eligibility policy**~~ — done 11 Nov: API and sync audit use `target_role_policy`; `evaluate_eligibility()` returns the four states with reasons. Remaining: expose the decision in the jobs API/UI.
2. ~~**Test isolation**~~ — done 10 Nov: single `resolve_database_path()` honouring `JOBPILOT_DATABASE_PATH`; `test_database` / `test_dedup_constraint` use a temp DB.
3. ~~**Source health model**~~ — done 13 Nov (`source_health` table, `GET /api/sources/health`, health recorded by the sync script). Remaining: connectors reporting pagination status; relax the 30-company check in `load_registry`.
4. ~~**Validate the 7 configured sources live**~~ — done 14 Nov: Amazon, Razorpay, Groww, BrowserStack promoted; Uber (confirm ownership manually), Adobe (re-run after Workday wd5 recovers), Freshworks (needs detail enrichment) still awaiting validation.
5. **Discover connectors for the unmapped companies / add companies** — partly done 15 Nov: 6 of the 19 mapped, 10 companies added, registry at 40, 18 active. Remaining: 13 unmapped (Microsoft connector for its `apply.careers.microsoft.com` API is the most promising), 10 more evidence-backed companies to reach 50 (do not pad), confirm ownership for Uber/Zscaler/GitLab/Twilio/InMobi, re-run NVIDIA after the Workday pagination fix.
6. ~~Company coverage dashboard~~ — done 15 Nov (`views/CoverageView.tsx`). 17-20 Nov work (frontend split, job versions/change detection, FAST/FULL, SmartRecruiters enrichment, scheduled sync and summary, configurable weights, eligibility cap, job comparison API) is described in PROJECT_STATUS.md Session 8. Still open: URL routing, sync-summary and comparison UIs, a shared location module.

## Progress note (16 Nov)
Done since the last note: AI provider layer + fit analysis, opportunity scoring/recommendations/skill gaps, resume versions with tailoring report and fail-closed fabrication check, cover letters, answer library, application status history (details in PROJECT_STATUS.md Session 9). Next: Chrome extension adapters (26 Nov), Gmail lifecycle hardening, analytics/CRM/interview prep, auth/migrations/deployment, docs.

## Phase 2 — Matching and AI
Config-driven score weights, validated on real jobs; skill-gap view from actual opportunity data; Ollama provider abstraction with health check, timeouts, schema validation and prompt versioning; keep deterministic filtering authoritative.

## Phase 3 — Resume and application preparation
Resume Studio UI (versions, preview, PDF/DOCX), cover letters, employer-answer library, readiness checklist. `ready_to_apply` never implies `applied`.

## Phase 4 — Chrome extension
Split `popup.js` into content script + portal adapters (Greenhouse, Lever, Workday first), field-level review, manual submit only, explicit "I submitted" confirmation to set `applied_at`.

## Phase 5 — Gmail lifecycle
Controlled live sync with the existing read-only scope; re-audit strict matching (applied record + employer + title + date), review queue, approve/ignore, audit trail.

## Phase 6 — Analytics and advanced intelligence
Funnel from real records with small-sample warnings, interview prep, recruiter CRM, scheduled monitoring and change detection.

## Phase 7 — Production
Auth, Postgres + migrations, deployment, backups, monitoring, docs, release checklist.

## Frontend design workstream (runs alongside Phase 1–3)
`frontend/src/App.tsx` is a single 4,025-line file. Split into routed pages and a shared component set before adding features. Design inputs requested for this: the "taste" skill, Vercel web-design-guidelines, awesome-design-md and playwright-cli (for UI verification). **Not yet installed or applied** — fetching them needs the user's go-ahead on source and version.

## Housekeeping (needs user decision)
Delete or archive `*.bak`, backup `.db` files, root `target_sync_*` reports and the empty `_jobpilot_extension_submission_patch/` folder; git history already preserves code.

## Progress note (17 Nov)
Built since the last note: extension matcher and portal detection, Gmail hardening (closed postings still match, undated mail never matches, suggested follow-ups), funnel analytics, contact book with draft-only outreach, interview preparation, optional API token, backup/restore, Docker files, full documentation set and a one-command offline regression. See PROJECT_STATUS.md for exactly what is verified.

Done since: needs-review job tab, still-open check, per-skill resume choices, India filter fix, collector retry/backoff (see PROJECT_STATUS.md Sessions 11-12).

Next, in priority order:
1. **Verify with your own accounts and browser** (list in PROJECT_STATUS.md): extension on real forms, live Gmail, the new screens, a real sync.
2. Reach 50 companies honestly: 10 more with verified public boards; write the Microsoft connector; confirm ownership for the held sources; re-run NVIDIA.
3. Screens for contacts and interview prep; history view in Applications; archive and the extra statuses.
4. Quality: URL routing, a design pass, a migration framework if existing columns ever need to change.
5. Only if needed: Postgres, multi-user accounts, a mock AI interviewer.
