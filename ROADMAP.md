# JobPilot — Roadmap

Ordered by impact. Core discovery and application pipeline first; advanced intelligence only after the data underneath is trustworthy. See `PROJECT_STATUS.md` for the current evidence.

## Phase 0 — Audit (done, session 1)
- Repository mapped, baseline recorded, role-filter regressions repaired and covered by a new guard test.

## Phase 1 — Core discovery (next)
1. ~~**Centralise the role/eligibility policy**~~ — done 11 Nov: API and sync audit use `target_role_policy`; `evaluate_eligibility()` returns the four states with reasons. Remaining: expose the decision in the jobs API/UI.
2. ~~**Test isolation**~~ — done 10 Nov: single `resolve_database_path()` honouring `JOBPILOT_DATABASE_PATH`; `test_database` / `test_dedup_constraint` use a temp DB.
3. ~~**Source health model**~~ — done 13 Nov (`source_health` table, `GET /api/sources/health`, health recorded by the sync script). Remaining: connectors reporting pagination status; relax the 30-company check in `load_registry`.
4. ~~**Validate the 7 configured sources live**~~ — done 14 Nov: Amazon, Razorpay, Groww, BrowserStack promoted; Uber (confirm ownership manually), Adobe (re-run after Workday wd5 recovers), Freshworks (needs detail enrichment) still awaiting validation.
5. **Discover connectors for the 19 unmapped companies** from official career pages; choose the 20 additional companies on the criteria in the brief (do not pad to 50).
6. Company coverage dashboard in the UI backed by the health table.

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
