# Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| The app shows "offline" / "Start the backend" | The backend is not running or is on another port. Start `uvicorn app.api.main:app --host 127.0.0.1 --port 8000` and check `http://127.0.0.1:8000/api/health`. If you changed the port, set `VITE_API_BASE_URL`. |
| Every request returns **401** | `JOBPILOT_API_TOKEN` is set but the request has no matching token. Unset it for local use, or build the frontend with `VITE_API_TOKEN` (see [DEPLOYMENT.md](DEPLOYMENT.md)). |
| AI shows **unavailable** on the first request | A cold local model can take minutes on CPU. Set `JOBPILOT_OLLAMA_TIMEOUT=400`, make sure Ollama is running (`python -m scripts.check_ollama`) and the model is pulled (`ollama pull gemma3:4b`). Everything except the AI wording works without it. |
| Recommended / Discover is empty | No stored job passes your filters yet. Run a sync (`python -m scripts.sync_target_companies --mode full`), then refresh. Many boards have no current 0-2 year software roles in India; check the audit with `--dry-run --audit-report out.csv` to see why jobs were filtered. |
| A company shows 0 jobs or "Awaiting validation" | Open **Company coverage** and read the state and last problem. A source only syncs automatically when it is `active` and verified in `data/target_companies.json`. |
| A sync fails for one company | Others continue. The company's last error is on the coverage page. Workday hosts sometimes return HTTP 5xx for a while; re-run later. |
| Tailored resume says "No verified evidence was selected" | Build and review your evidence first (`scripts.build_master_resume_store`, `scripts.review_master_resume_evidence`) and mark relevant items verified. |
| Resume generation returns 422 "not backed by your verified evidence" | The integrity check found a bullet that is not verified evidence. Nothing was saved. Re-select evidence for the job and try again. |
| Gmail "Connect" fails | Check `credentials/gmail_oauth_client.json` exists, the redirect URI registered with Google is exactly `http://127.0.0.1:8000/api/email/oauth/callback`, and your address is a test user while the consent screen is in testing. |
| Gmail sync finds no events | Only mail that names the company and role of an application you marked **Applied** becomes an event, and its date must not be before the submission. Mark the application applied first. |
| The extension says "no editable fields" | You are probably on the job description page. Click the employer's Apply button, sign in yourself if asked, and reopen the extension on the actual form. |
| The extension fills nothing on a portal | Some portals use custom controls or an embedded frame the extension cannot read. Fill those fields by hand. Unrecognised portals only get clearly labelled fields. |
| `database is locked` | Another process is writing. Close other JobPilot processes and retry; syncs write sequentially. |
| A test fails on `UNIQUE constraint failed` | You ran an old script against a populated database. Use `python -m scripts.run_offline_tests`, which uses a temporary copy. |
| Something looks wrong after a sync | Restore: `python -m scripts.backup_database --list`, then `--restore <file> --yes`. A `pre_restore_*.db` copy of the replaced data is kept. |

If a problem is not listed, run `python -m scripts.run_offline_tests` and the frontend `npm run build` first: a failing test usually names the cause.
