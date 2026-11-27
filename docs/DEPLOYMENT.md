# Deployment

JobPilot is designed as a **private, single-user** tool. The default is to run it on your own machine (see [INSTALLATION.md](INSTALLATION.md)). This page covers running it in containers, protecting the API, backups and scheduled syncs. Do not describe a setup as production-ready until you have worked through [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Docker Compose

```powershell
Copy-Item .env.example .env        # then edit .env (never commit it)
docker compose up --build
```

- Backend on `127.0.0.1:8000`, frontend on `127.0.0.1:5173`. Both ports are deliberately bound to the loopback address.
- The database lives in the `jobpilot_storage` volume. Your resume evidence (`data/master_resume`) and generated documents (`data/generated_resumes`) stay on the host.
- Ollama runs on the host; the backend reaches it at `host.docker.internal:11434`.
- Gmail credentials and tokens are **not** baked into the image (`.dockerignore`). Mount them yourself if you use Gmail from the container.

> **Not yet verified:** the Dockerfiles and compose file were written and syntax-checked, but the images have not been built in this repository's test environment (no Docker daemon was running). Build them once and check `docker compose ps` shows the backend healthy before relying on them.

## Protecting the API

Local use needs no token. For anything reachable beyond your own machine:

1. Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Set `JOBPILOT_API_TOKEN` for the backend and `VITE_API_TOKEN` when building the frontend.
3. Every `/api` request now needs `Authorization: Bearer <token>`. `/api/health` and the Gmail OAuth redirect stay open.
4. Set `JOBPILOT_CORS_ORIGINS` to your real frontend address.
5. Put a TLS reverse proxy (Caddy, nginx, Traefik) in front, and register the HTTPS callback with Google if you use Gmail.

Limits to know: the token is a single shared secret, not per-user login; a `VITE_` value is visible in the frontend's JavaScript; browser download links (resumes, cover letters) cannot carry the header; and the Chrome extension does not send a token yet, so it only works against a backend with the token off. For a shared, multi-user service you would need real authentication and per-user data separation, which JobPilot does not have.

## Backups and restore

```powershell
.\venv\Scripts\python.exe -m scripts.backup_database                  # verified copy in backups\, keeps the latest 14
.\venv\Scripts\python.exe -m scripts.backup_database --list
.\venv\Scripts\python.exe -m scripts.backup_database --restore backups\jobpilot_YYYYMMDD_HHMMSS_ffffff.db --yes
```

Backups use SQLite's online backup, are integrity-checked before they are kept, and a restore first saves the current database as `pre_restore_*.db`. Back up before every large sync or upgrade. Copy `backups\` somewhere off the machine yourself; JobPilot does not do offsite storage.

## Scheduled syncs

For the normal daily update on your own Windows PC, use `scripts\register_daily_update.ps1` (see the README). Do not also schedule the command below; the two do not know about each other.

`scripts/run_scheduled_sync.py` syncs the verified sources and saves a summary of what changed under `data\sync_reports\`. Example (daily 08:00, FAST mode):

```powershell
schtasks /Create /SC DAILY /ST 08:00 /TN "JobPilot daily sync" /TR "D:\Full stack Projects\Automatic Job Apllication\venv\Scripts\python.exe -m scripts.run_scheduled_sync --mode fast --summary-days 1"
```

Run a weekly `--mode full` as well: FAST reuses stored descriptions and cannot see an edited posting or detect removed jobs. Take a backup first if the sync writes to a database you care about.

## Postgres, workers, monitoring

JobPilot runs on SQLite. The data layer uses SQLAlchemy, so Postgres is plausible, but it has **not** been tried, and the tracker and Gmail modules use SQLite-specific SQL directly. There is no background worker, queue or error-monitoring integration; syncs are explicit commands. Add those only when you have a concrete need.
