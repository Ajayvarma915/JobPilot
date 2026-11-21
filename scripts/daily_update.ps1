# Daily job update for JobPilot: backs up the database, reads every company career page and the
# remote job boards, closes jobs that were taken down. Safe to run by hand or from Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File scripts\daily_update.ps1
#
# Output is appended to data\daily_update.log. Nothing is submitted or sent anywhere.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root "venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Could not find $python. Create the venv first (see docs/installation.md)." }
$log = Join-Path $root "data\daily_update.log"
"" | Out-File -FilePath $log -Append -Encoding utf8
"===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') daily update =====" | Out-File -FilePath $log -Append -Encoding utf8
& $python -u -m scripts.run_job_update 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
