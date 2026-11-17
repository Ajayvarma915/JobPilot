# Release checklist

JobPilot is a personal tool that has been verified in layers. This list separates what automated tests prove from what only you can confirm with your own accounts and browser. Do not call a build "ready" because the first group passes.

## 1. Automated (run these every time)

- [ ] `.\venv\Scripts\python.exe -m scripts.run_offline_tests` reports 0 failed (skips are listed, never counted as passes).
- [ ] `cd frontend; npm run lint; npm run build` both succeed.
- [ ] `git status` shows no secret or personal file (see [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md)).
- [ ] `python -m scripts.generate_api_docs` leaves `docs/API.md` unchanged (or commit the update).

## 2. Needs your own accounts or a real browser (not covered by automated tests)

- [ ] **Extension on a real form:** on a Greenhouse, a Lever and a Workday application, confirm the right fields fill, nothing is submitted, and "Confirm I submitted" records the time. Tests only use synthetic labels.
- [ ] **Gmail live:** connect your account, run a sync, confirm a real recruiter email matches the right application and waits for approval. Tests use mocked mail.
- [ ] **Local AI live:** run an AI fit analysis on a real job (`POST /api/jobs/{id}/ai-fit`). The first call can be slow on CPU; see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- [ ] **Sources live:** `python -m scripts.sync_target_companies --dry-run --audit-report out.csv` and check the active companies return jobs. Career sites change; a source can break at any time.
- [ ] **New screens in a browser:** click through Recommended, Cover letters & answers, Resume studio (versions panel), Insights and Company coverage.
- [ ] **Docker:** `docker compose up --build`, then `docker compose ps` shows the backend healthy and the app works at http://127.0.0.1:5173. The images are unbuilt in this repo's test environment.

## 3. Before a large change or upgrade

- [ ] `python -m scripts.backup_database` (and copy `backups\` off the machine).
- [ ] Note the current commit (`git rev-parse HEAD`) so you can return to it.

## 4. Rollback

1. Code: `git checkout <previous commit>` (or `git revert`).
2. Data: `python -m scripts.backup_database --restore backups\<file> --yes` (your current data is saved as `pre_restore_*.db` first).
3. Frontend: rebuild with `npm run build`.

## 5. Known gaps in this release

- No schema migration framework: new tables are created on first use and nothing is altered or dropped. A change to an existing column would need a hand-written migration.
- SQLite only; Postgres has not been tried.
- Single user; no accounts. The optional API token is one shared secret.
- No error-monitoring or structured-log shipping; logs go to the console.
- 13 of the 40 registry companies have no connector, 8 await validation, and the 50-company goal is not met.
- The mock-interview feature (an AI interviewer) was not built; interview preparation is a deterministic plan with progress tracking.
