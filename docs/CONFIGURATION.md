# Configuration reference

Every setting is optional. Put them in `.env` (copy `.env.example`; `.env` is git-ignored) or set them in the environment. Docker Compose reads `.env` automatically.

## Backend

| Variable | Default | Purpose |
|---|---|---|
| `JOBPILOT_DATABASE_PATH` | `jobpilot.db` in the project folder | SQLite file to use. Tests set this to a temporary file so they never touch your data. |
| `JOBPILOT_API_TOKEN` | empty (off) | When set, every `/api` request must send `Authorization: Bearer <token>` (or `X-JobPilot-Token`). `/api/health` and the Gmail OAuth redirect stay open. |
| `JOBPILOT_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins allowed to call the API. |
| `JOBPILOT_AI_PROVIDER` | `ollama` | `ollama` or `none` (AI off). No paid or external provider exists unless you register one in code. |
| `JOBPILOT_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Where Ollama listens. |
| `JOBPILOT_OLLAMA_MODEL` | `gemma3:4b` | Local model to use. |
| `JOBPILOT_OLLAMA_TIMEOUT` | `180` | Seconds before a model call is abandoned. Use `400` if a cold model on CPU times out. |
| `JOBPILOT_GOOGLE_CLIENT_SECRETS` | `credentials/gmail_oauth_client.json` | Google OAuth client file. |
| `JOBPILOT_GMAIL_TOKEN_PATH` | `tokens/gmail_token.json` | Where the Gmail access token is stored. |
| `JOBPILOT_GMAIL_REDIRECT_URI` | `http://127.0.0.1:8000/api/email/oauth/callback` | Must match the redirect URI registered with Google. |

## Frontend (build time)

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | API address. |
| `VITE_API_TOKEN` | empty | Sent as the bearer token. **It is compiled into the public JavaScript**, so use it only for a private single-user deployment. |

## Data files you can edit

| File | Purpose |
|---|---|
| `data/target_companies.json` | The company registry: connector, settings, status and evidence notes per company. A source is only synced automatically when it is `active` and `verified`. |
| `data/match_weights.json` | The six match-score weights (must add up to 100). Editing it re-scores jobs. A corrupt file is reported as an error rather than silently ignored. |

## Command-line options worth knowing

| Command | Options |
|---|---|
| `scripts.sync_target_companies` | `--mode full\|fast`, `--concurrency 1-8`, `--only <company id>`, `--dry-run`, `--include-unverified` (dry run only), `--record-health`, `--no-removal-detection`, `--audit-report <csv>` |
| `scripts.backup_database` | `--keep N`, `--list`, `--restore <file> --yes` |
| `scripts.run_scheduled_sync` | `--mode`, `--concurrency`, `--summary-days` |
| `scripts.run_offline_tests` | `-k <text>`, `--timeout <seconds>` |
