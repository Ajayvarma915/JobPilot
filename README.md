# JobPilot

JobPilot is a local-first job discovery and application-preparation assistant. It finds suitable software roles at product companies, explains how well each one fits you, helps you prepare honest application materials, and tracks every application, **while you stay in control of every submission.**

> **What it will never do:** submit an application for you, send an email or recruiter message for you, invent a skill, employer, number or qualification, or bypass a CAPTCHA, login or anti-bot control. A job marked `ready_to_apply` is *not* applied; only your own confirmation records an application as applied.

## What it does

| Area | What you get |
|---|---|
| **Discovery** | A registry of 40 companies (19 active, validated against live career sites). Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Oracle HCM, Amazon and Atlassian connectors. Deduplication, version history, change and removal detection, FULL and FAST sync modes. |
| **Eligibility** | One rule set decides role family, seniority, experience (0-2 years), PhD requirements and India/remote eligibility, with a stated reason for every exclusion. Undisclosed salary never excludes a job. |
| **Matching** | An explainable 0-100 score with configurable weights, mandatory-vs-preferred skill gaps, an eligibility cap so keyword overlap can never rescue an excluded job, and side-by-side comparison. |
| **Recommendations** | Each job gets a next action (apply now, review first, prepare missing skills, skip) with reasons, plus skill gaps counted from your real jobs. |
| **Local AI** | Optional analysis with a local Ollama model. Output is validated against the job text and your profile, the rules win every conflict, and everything works with AI switched off. |
| **Documents** | Evidence-based tailored resumes (Word and PDF) with a report of what was reused and a check that blocks any unverified claim; cover letters built only from verified facts; an approved-answer library. |
| **Applications** | A tracker with a readiness checklist, status history, follow-ups, and funnel analytics that hide percentages until the sample is large enough to mean something. |
| **Browser extension** | Fills clearly labelled fields on supported application forms. It never clicks Submit, uploads files or answers sensitive questions. |
| **Email (read-only)** | Gmail read-only matching of recruiter emails to your submitted applications, with every status change waiting for your approval. |
| **Contacts and prep** | A recruiter/referral contact book (drafts are text only until you send them yourself) and a practice plan per application. |

An honest account of what has and has not been verified is in [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Quick start (Windows PowerShell)

```powershell
cd "D:\Full stack Projects\Automatic Job Apllication"
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Full instructions, including Ollama, Gmail and the browser extension, are in [docs/INSTALLATION.md](docs/INSTALLATION.md).

## Bringing in jobs

```powershell
# Back up first, then sync every verified, active company source into your database.
.\venv\Scripts\python.exe -m scripts.backup_database
.\venv\Scripts\python.exe -m scripts.sync_target_companies --mode full --concurrency 3

# See what a source would return without writing anything:
.\venv\Scripts\python.exe -m scripts.sync_target_companies --dry-run --only databricks
```

Only jobs that pass every rule with no review flags are written. For unattended runs see `scripts/run_scheduled_sync.py` (Windows Task Scheduler command inside).

## Testing

```powershell
.\venv\Scripts\python.exe -m scripts.run_offline_tests
cd frontend; npm run lint; npm run build
```

`run_offline_tests` runs every offline test against a **temporary copy** of your database, so it cannot change your data. Tests that need live career sites, a running Ollama or your personal resume are skipped and listed; they are not counted as passes.

## Documentation

| Document | Contents |
|---|---|
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Setup on Windows: backend, frontend, Ollama, Gmail, extension |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, data flow and tables |
| [docs/API.md](docs/API.md) | Every endpoint (generated from the code) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, API token, reverse proxy, backups, scheduling |
| [docs/SECURITY_CHECKLIST.md](docs/SECURITY_CHECKLIST.md) | Security and privacy checklist |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common problems and fixes |
| [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) | What to verify before relying on a release |
| [docs/CLEANUP_PROPOSAL.md](docs/CLEANUP_PROPOSAL.md) | Stale files you may want to remove |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) / [ROADMAP.md](ROADMAP.md) | Verified status and what is next |

## Secrets and personal data

Never commit or share `.env`, `credentials/`, `tokens/`, Gmail OAuth files, personal resumes, generated documents, `jobpilot.db`, `backups/`, `venv/`, `node_modules/` or `.git/`. All of these are git-ignored; `.env.example` documents every setting with placeholders only.
