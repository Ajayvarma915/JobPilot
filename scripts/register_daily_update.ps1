# Registers a Windows scheduled task that runs scripts\daily_update.ps1 every day.
# You run this yourself, once:
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_daily_update.ps1            # daily at 08:00
#   powershell -ExecutionPolicy Bypass -File scripts\register_daily_update.ps1 -At 07:30
#   powershell -ExecutionPolicy Bypass -File scripts\register_daily_update.ps1 -Remove    # undo
#
# The task runs as you, only while you are logged in, and can be inspected or deleted in Task Scheduler.
param([string]$At = "08:00", [switch]$Remove)
$name = "JobPilot daily job update"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    "Removed the scheduled task '$name'."
    return
}
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\daily_update.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description "Reads company career pages and remote job boards into JobPilot." -Force | Out-Null
"Scheduled '$name' daily at $At. Run it now with:  Start-ScheduledTask -TaskName '$name'"
