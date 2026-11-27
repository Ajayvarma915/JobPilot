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

Jobs that pass every rule are written; ones with something unclear (often no stated years of experience) are written too but wait in the **Needs your review** tab until you accept or dismiss them.

## Daily use

1. **Update jobs:** press **Update jobs now** on the Discover screen (backs up the database first, reads every company page and the remote job boards, closes jobs that were taken down). To do it automatically every morning, run once: `powershell -ExecutionPolicy Bypass -File scripts\register_daily_update.ps1` (add `-At 07:30` for another time, `-Remove` to undo). The scheduled run is the same update as the button, is skipped if one is already running, and keeps its history in `data\daily_update.log`. It runs only while you are logged in; a run missed while the PC was off starts when it is next available.
2. **Confirm your resume:** after you change the PDF in `data/master_resume`, run `.\venv\Scripts\python.exe -m scripts.build_master_resume_store`, then confirm the statements in the panel at the top of the Resume screen. Tailored resumes use only confirmed statements.
3. **Find, tailor, apply:** Discover (filter by company, "Only new"), **Tailor**, apply on the employer's own site, then press Confirm in the extension or track it by hand. JobPilot never submits anything.
4. **A job from a company with no public list:** open its page and press **Save this job** in the browser extension, or paste the link under **Add a job by link**.
5. **Gmail:** the app reads new mail by itself while it is open. Track a job, apply on the company site, and the confirmation email marks it Applied; clear interview, assessment, offer or rejection emails move it on. Everything automatic is listed under Approved (switch it off on the Email screen). Confirmations for jobs you do not track appear as suggestions you can add.
6. **Remote jobs:** the Remote tab is filled from Remotive, Remote OK, Himalayas, We Work Remotely, Y Combinator's public jobs pages, Jobicy and Working Nomads. Wellfound cannot be used (login wall and no scraping allowed).

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
