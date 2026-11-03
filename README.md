# JobPilot

JobPilot is a local-first job discovery, evidence-based resume tailoring, application-preparation and application-tracking platform. It is designed to keep the candidate in control of employer submissions.

## Current architecture

- **Backend:** Python, FastAPI, SQLAlchemy and SQLite
- **Frontend:** React, TypeScript and Vite
- **Local AI:** Ollama (configured model: `gemma3:4b`) for on-demand structured job-description analysis
- **Job sources:** Google Careers, Greenhouse and Lever collectors
- **Resume workflow:** candidate evidence store, tailored DOCX/PDF generation and ATS evaluation
- **Email intelligence:** Gmail read-only OAuth integration; application events remain subject to review
- **Browser assistance:** browser-extension foundations for supported application-form workflows

## Default job-search policy

The default opportunity feed is intentionally narrower than the raw job-board inventory:

- Software-engineering title families only (SWE, SDE, backend, frontend, full-stack, platform, SRE/DevOps, AI/ML/data engineering, security software engineering and test automation).
- Excludes support, customer service/success, sales, account executive, recruiting, marketing, finance, administrative and other non-software roles.
- Defaults to India and India-eligible remote locations; location-restricted roles in other countries are excluded from the default feed.
- Early-career mode uses the candidate's TCS start date (18 September 2025) and currently allows roles whose stated minimum experience requirement is up to two years.
- Compensation defaults to **₹25 LPA or higher, or undisclosed**. Explicitly disclosed ranges below ₹25 LPA are hidden by default; unknown ranges stay visible because many postings do not publish salary. Listings with disclosed ranges are labelled as ₹25+ or ₹30+ when detectable.

Salary detection only reads explicit INR/LPA expressions in the saved job description. It does not infer pay, convert foreign currencies, or determine whether a disclosed figure is fixed pay, variable pay or equity. Verify the employer's compensation structure before applying.

The configured source registry currently contains Google Careers, Coinbase's Greenhouse board and KnowBe4's Greenhouse board; Lever is implemented but has no company entries configured yet. A source board can publish every department's vacancies, so the role policy filters board output before it reaches the default feed. Expand `data/job_sources.json` with verified target-company career/ATS identifiers to increase coverage.

## Windows development setup

### Backend

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```powershell
cd frontend
npm ci
npm run dev
```

### Local AI

Install Ollama, pull the configured model and check it:

```powershell
ollama pull gemma3:4b
python -m scripts.check_ollama
```

## Useful verification commands

Run tests from the project root using module invocation:

```powershell
python -m scripts.test_job_filter_policy
python -m scripts.test_multi_source_collectors
python -m scripts.test_ollama_jd_analysis
python -m scripts.test_email_integration
```

Build the frontend:

```powershell
cd frontend
npm run build
```

## Secrets and local data

Never commit or share `.env`, `credentials/`, `tokens/`, Gmail OAuth client secrets, Gmail token files, personal resumes, generated resumes, `jobpilot.db`, `venv/`, `node_modules/` or `.git/`. Keep private credentials local. The Gmail integration requests read-only access and does not store full email bodies or attachments.

## Application-submission boundary

JobPilot discovers roles and prepares application materials. The user must review the employer form and explicitly submit it. A job marked `ready_to_apply` is not a submitted application; mark it `Applied` only after the employer has accepted the submission. Gmail lifecycle matching is restricted to confirmed JobPilot submissions.
    