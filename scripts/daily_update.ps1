# Daily job update for JobPilot: the same update as the app's "Update jobs now" button. It backs up the database,
# reads every company career page and the remote job boards, closes jobs that were taken down and scores new ones.
# Safe to run by hand or from Task Scheduler; it is skipped if an update is already running.
#
#   powershell -ExecutionPolicy Bypass -File scripts\daily_update.ps1
#
# Output is appended to data\daily_update.log. Nothing is submitted or sent anywhere.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Could not find $python. Create the venv first (see docs/installation.md)." }
# Python writes data\daily_update.log itself. Do not add "2>&1" here: with ErrorActionPreference = "Stop",
# Windows PowerShell then ends the whole update at the first harmless warning.
$ErrorActionPreference = "Continue"
& $python -u -m scripts.run_daily_update
exit $LASTEXITCODE
