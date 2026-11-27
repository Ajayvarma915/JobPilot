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
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
# By default Windows will not start a task on battery and stops it when you unplug, so both are switched off.
# A run missed because the PC was off or asleep starts when it is next available.
# No "only when the network is available" condition: in testing, the task was ended when Wi-Fi dropped.
# The update itself waits for the network instead.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Description "Reads company career pages and remote job boards into JobPilot." -Force | Out-Null
"Scheduled '$name' daily at $At. Run it now with:  Start-ScheduledTask -TaskName '$name'"
