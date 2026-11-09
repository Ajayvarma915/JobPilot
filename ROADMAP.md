# JobPilot — Roadmap

Ordered by impact. Core discovery and application pipeline first; advanced intelligence only after the data underneath is trustworthy. See `PROJECT_STATUS.md` for the current evidence.

## Phase 0 — Audit (done, session 1)
- Repository mapped, baseline recorded, role-filter regressions repaired and covered by a new guard test.

## Phase 1 — Core discovery (next)
1. **Centralise the role/eligibility policy**: make `app/api/main.py` call `target_role_policy` instead of keeping its own regexes; add `eligible / eligible_needs_review / excluded / source_unverified` results with reasons.
2. **Test isolation**: make `DATABASE_URL` configurable (`JOBPILOT_DB_PATH`) and point tests at a temp DB; fix `test_database` / `test_dedup_constraint`.
3. **Source health model**: persist per-company status (discovered → configured → awaiting_validation → verified → active → temporarily_unavailable → failed → deprecated), last success/failure, raw/unique/eligible/review counts, enrichment success. Migrate registry vocabulary.
4. **Validate the 7 configured sources live** (Amazon, Uber, Adobe, BrowserStack, Razorpay, Groww, Freshworks) with a read-only dry run; promote only on evidence.
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
