# Installation (Windows)

All commands are PowerShell, run from the project folder. Python 3.11 or newer and Node.js 20 or newer are required.

## 1. Backend

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt        # only to run the tests
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Check it: open http://127.0.0.1:8000/docs, or `curl http://127.0.0.1:8000/api/health`.

The database file `jobpilot.db` is created in the project folder on first use. New tables are added automatically and safely (create-if-missing); nothing is dropped. See [CONFIGURATION.md](CONFIGURATION.md) to place it elsewhere.

## 2. Frontend

```powershell
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The page talks to `http://127.0.0.1:8000` unless `VITE_API_BASE_URL` says otherwise.

## 3. Local AI (optional)

JobPilot works without AI. To add job and fit analysis:

```powershell
ollama pull gemma3:4b
python -m scripts.check_ollama
```

The first request after the model has been idle can take several minutes on a CPU. If the app reports AI as unavailable on that first request, set `JOBPILOT_OLLAMA_TIMEOUT=400` (see [CONFIGURATION.md](CONFIGURATION.md)). Set `JOBPILOT_AI_PROVIDER=none` to turn AI off.

## 4. Your resume evidence

Place your resume (PDF) in `data/master_resume/` (this folder is git-ignored), then:

```powershell
python -m scripts.build_master_resume_store
python -m scripts.review_master_resume_evidence
```

Only evidence you mark as verified is ever used in tailored resumes, cover letters and answers.

## 5. Gmail (optional, read-only)

1. In Google Cloud Console create a project, enable the **Gmail API**, and create an OAuth client of type **Web application** with the redirect URI `http://127.0.0.1:8000/api/email/oauth/callback`.
2. Download the client JSON and save it as `credentials/gmail_oauth_client.json` (git-ignored).
3. Start the backend, open the **Email intelligence** screen and choose **Connect Gmail**. JobPilot requests only the `gmail.readonly` scope; the token is stored in `tokens/gmail_token.json`.
4. **Sync** pulls recent messages. Only mail that matches one of your *submitted* applications (company and role evidence, and a sensible date) becomes a pending event; nothing changes until you approve it. Full email bodies are never stored.

The OAuth consent screen is in "Testing" mode unless you publish it; add your own address as a test user.

## 6. Browser extension (optional)

1. Open `chrome://extensions`, turn on **Developer mode**, choose **Load unpacked** and select `browser_extension/jobpilot-form-assistant`.
2. Make sure the backend is running, open an employer application page, click the extension, pick the tracked application and press **Fill supported fields**.
3. Review every field, attach your resume yourself and submit the form yourself. Afterwards use **Confirm I submitted this application** so JobPilot records the real submission time.

The extension is limited to `http://127.0.0.1:8000` and the active tab. It has been tested on synthetic examples and unit tests only; try it on a real form before relying on it.

## 7. Verify the installation

```powershell
.\venv\Scripts\python.exe -m scripts.run_offline_tests
cd frontend; npm run lint; npm run build
```
