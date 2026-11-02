# JobPilot

JobPilot is a local-first job discovery, resume-personalization, application-preparation, and application-tracking platform.

The current application uses a **FastAPI backend**, **SQLite/SQLAlchemy**, and a **React + TypeScript + Vite frontend**. It also includes a Manifest V3 browser form assistant and a read-only Gmail integration.

## Implemented in the current codebase

- Job-source adapters for Google Careers, Greenhouse, and Lever.
- Configurable source ingestion, job normalization, deduplication, and SQLite upserts.
- Rule-based job-description analysis and candidate/job matching.
- Candidate-profile and master-resume evidence selection.
- DOCX/PDF tailored-resume generation and resume evaluation.
- Application tracking, readiness review, and application-preparation records.
- Gmail OAuth, read-only message synchronization, lifecycle-event classification, application matching, and user-reviewed status updates.
- A Manifest V3 browser extension that fills supported visible application fields. It does not submit forms or upload the resume automatically.

## Known gaps / not yet complete

- `app/ai/ollama_client.py` is a basic local client; the current main job-analysis/matching flow does not call it yet. Do not describe the current matcher as LLM-powered.
- Lever collection is implemented, but `data/job_sources.json` currently has no enabled Lever entries.
- Gmail synchronization is currently initiated manually. A reliable scheduler and notification workflow are still to be built.
- The browser extension is a form-assistance layer, not a general-purpose Playwright automation engine. CAPTCHA, MFA, uploads, and final submission remain manual.
- CI, deployment, Docker, consolidated automated tests, and full application analytics remain future work.

## Prerequisites

- Windows 10/11 or another supported desktop OS.
- Python 3.11 or newer (the current development environment used Python 3.13).
- Node.js 20.19+ or 22.12+ and npm for the Vite frontend.
- Git and VS Code are recommended.
- Ollama is optional at this stage; the application does not yet use it in the main analysis workflow.

## Backend setup (Windows PowerShell)

Run from the repository root:

```powershell
python --version

python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

For development and tests:

```powershell
pip install -r requirements-dev.txt
```

Initialize the database only for a new local setup:

```powershell
python -m app.db.init_db
```

`create_all()` creates missing tables and does not delete existing tables or records. Still, back up `jobpilot.db` before making schema or migration changes.

Start the API:

```powershell
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

API health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## Frontend setup

Open a second PowerShell terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Vite serves the app at `http://127.0.0.1:5173` (the port is configured as strict in `vite.config.ts`). The frontend defaults to the API at `http://127.0.0.1:8000`; set `VITE_API_BASE_URL` in a local `frontend/.env.local` only when you need a different API address.

Production build check:

```powershell
npm run build
npm run lint
```

## Job-source configuration

Edit `data/job_sources.json` to enable the sources you want to collect. Current adapters are:

- `google`: Google Careers query and location settings.
- `greenhouse`: one entry per public Greenhouse board, using its board token.
- `lever`: one entry per public Lever site, with the supported region.

Run a collection without writing to the database:

```powershell
python -m scripts.sync_job_sources --dry-run
```

Only run a non-dry sync after checking the selected sources and database backup:

```powershell
python -m scripts.sync_job_sources
```

The number of companies collected depends on the sources explicitly configured in `data/job_sources.json`; the adapters do not automatically discover every product company on the internet.

## Gmail setup

Gmail uses read-only OAuth. Keep these files local and private:

```text
credentials/gmail_oauth_client.json
 tokens/gmail_token.json
```

The OAuth client must be a Google Cloud **Web application** client with this exact local redirect URI:

```text
http://127.0.0.1:8000/api/email/oauth/callback
```

Connect Gmail from JobPilot's Employer Email Events page. The token is generated after authorization. Never commit or share the OAuth client secret or token file.

Gmail sync can produce pending lifecycle events, but events must be reviewed before they update an application. Only applications that you actually submitted and marked `Applied` in JobPilot are eligible for lifecycle matching.

## Browser form assistant

The extension source is in `browser_extension/jobpilot-form-assistant/`.

1. Open `brave://extensions` or `chrome://extensions`.
2. Enable Developer mode.
3. Choose **Load unpacked**.
4. Select the `browser_extension/jobpilot-form-assistant` folder.
5. Open an employer application form, then use the extension to fill supported fields.

Review every field. The extension does not click Submit, bypass CAPTCHA/MFA, or upload a resume automatically.

## Tests and local checks

Run from the repository root:

```powershell
python -m scripts.test_email_integration
python -m scripts.test_multi_source_collectors
```

The Gmail integration suite currently contains 15 regression tests. The collector script currently contains two deterministic Greenhouse/Lever adapter tests. Other `scripts/test_*.py` files include a mixture of unit tests, database-dependent checks, and manual diagnostics; not every script is a self-contained test suite yet.

Run the environment preflight:

```powershell
python -m scripts.check_environment
```

## Local files that must not be committed or shared

Keep the following local:

- `.env` and `frontend/.env.local` (the latter may contain local configuration).
- `credentials/` and `tokens/`.
- `jobpilot.db` and other local SQLite databases.
- `data/master_resume/` and generated resumes/cover letters.
- `venv/`, `frontend/node_modules/`, and `.git/` are not needed in a source ZIP.

The `.gitignore` covers these paths for future Git commits. If a private file was committed previously, `.gitignore` alone does not remove it from Git history; check the repository's tracked files separately.
