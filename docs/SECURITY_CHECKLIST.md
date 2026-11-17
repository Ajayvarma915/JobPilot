# Security and privacy checklist

Use this before sharing the repository or exposing JobPilot beyond your own machine. Items marked **(built in)** are enforced by the code and covered by tests; the others are things only you can do.

## Secrets and personal data

- [ ] `.env`, `credentials/`, `tokens/`, `jobpilot.db`, `backups/` and `data/master_resume/` are not tracked: `git ls-files | Select-String "\.env|credentials|tokens|\.db"` shows nothing. **(git-ignored and Docker-ignored)**
- [ ] No secret is printed or logged. AI logs record only task, version, model, sizes and timing, never prompt or answer text. **(built in)**
- [ ] `.env.example` contains placeholders only.
- [ ] Generated resumes, cover letters and reports are treated as personal data and stay under git-ignored folders.
- [ ] Back up `jobpilot.db` before upgrades (`scripts.backup_database`) and keep a copy off the machine.

## Gmail

- [ ] The OAuth client requests only `gmail.readonly`. **(built in)**
- [ ] Full email bodies are never stored: only subject, sender and a short snippet, and only for matched events. **(built in, tested)**
- [ ] Mail changes nothing until you approve the event. **(built in)**
- [ ] If you disconnect, revoke the app at https://myaccount.google.com/permissions as well.

## Automation boundaries

- [ ] The extension never clicks, submits, uploads files or answers sensitive questions (gender, race, disability, date of birth, ...). **(built in, tested statically and by label corpus)**
- [ ] Nothing sends email or recruiter messages: outreach is a draft until you send it yourself. **(built in)**
- [ ] `ready_to_apply` never records a submission; only your explicit status change or confirmation does. **(built in, tested)**
- [ ] No CAPTCHA, login or anti-bot bypass exists anywhere.
- [ ] Collectors call only public career endpoints with timeouts and sensible limits; respect each site's terms.

## Truthfulness

- [ ] Resumes pass the fail-closed check (every bullet is verified evidence). **(built in, tested)**
- [ ] Cover letters and answers use only verified facts; salary, notice period and work authorization are never guessed. **(built in, tested)**
- [ ] AI output is validated and the rules win every conflict; the product works with AI off. **(built in, tested)**

## Network exposure

- [ ] The servers listen on `127.0.0.1` only unless you deliberately change it.
- [ ] If anything is reachable from another machine: set `JOBPILOT_API_TOKEN`, set `JOBPILOT_CORS_ORIGINS`, and put a TLS reverse proxy in front. The token is one shared secret, not per-user login.
- [ ] Do not expose JobPilot to the internet as a multi-user service: it has no accounts, per-user data separation or rate limiting.

## Known gaps

- No automatic dependency or vulnerability scanning; run `pip list --outdated` and `npm audit` yourself from time to time.
- The API token is not supported by the browser extension and cannot protect browser download links.
- The container images have not been built or scanned in this repository's test environment.
