# Cleanup proposal

Nothing here has been deleted. These are files that look like leftovers; **you decide**. Git history already preserves every tracked file, so removing a tracked file from the working tree loses nothing.

## Tracked in git (safe to remove with `git rm`)

| Files | Why they look stale |
|---|---|
| `app/api/main.py.bak`, `app/api/main.py.before_application_tracker_20261016_095921.bak`, `app/api/main.py.before_match_cache.bak`, `app/api/main.py.before_resume_upgrade.bak` | Manual backups of `main.py`; the committed history is the real backup. |
| `frontend/src/App.tsx.bak`, `frontend/src/App.tsx.before_applications_20261023_083815.bak` | Manual backups of the old single-file `App.tsx`, which has since been split into modules. |
| `requirements.txt.before_resume_upgrade.bak` | Manual backup. |
| `target_sync_audit.csv`, `target_sync_audit_v2.csv` ... `target_sync_audit_v7_fast.csv`, `target_sync_verified_v1.csv`, `target_sync_dry_run_final.txt`, `target_sync_dry_run_retry.txt` | One-off sync audit reports in the repository root. They are regenerable (`--audit-report`) and contain job data. |

```powershell
git rm app/api/main.py.bak app/api/main.py.before_application_tracker_20261016_095921.bak app/api/main.py.before_match_cache.bak app/api/main.py.before_resume_upgrade.bak
git rm frontend/src/App.tsx.bak frontend/src/App.tsx.before_applications_20261023_083815.bak requirements.txt.before_resume_upgrade.bak
git rm target_sync_audit.csv target_sync_audit_v2.csv target_sync_audit_v3.csv target_sync_audit_v4.csv target_sync_audit_v5.csv target_sync_audit_v6.csv target_sync_audit_v7_fast.csv target_sync_verified_v1.csv target_sync_dry_run_final.txt target_sync_dry_run_retry.txt
```

## Present on disk but ignored by git (delete only if you no longer want them)

| Item | Note |
|---|---|
| `data/target_companies.json.before_discovery.bak` | Backup of the registry before ATS discovery; the registry is in git. |
| `jobpilot_before_lifecycle.db`, `jobpilot_before_multisource_*.db` | Old database snapshots. Keep them only if you want that history; `scripts.backup_database` replaces this habit. |
| `_jobpilot_extension_submission_patch/` | An empty folder. |

## Worth tidying, not deleting

- `scripts_test_extension_submission_confirmation.mjs` is a real test that lives in the repository root. Moving it into `scripts/` would match the other tests (update the path in `scripts/run_offline_tests.py` when you do).
- Reports from `--audit-report` should be written outside the repository (for example a `reports\` folder you add to `.gitignore`).
