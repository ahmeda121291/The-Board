# Boardroom — register the daily checkpoint as a Windows Scheduled Task.
# Run once. Re-run to change the time. Default 17:00 local (~21:00 UTC in EDT,
# matching CHECKPOINT_UTC so the dashboard countdown lines up).
#
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1 -Time 16:30
param([string]$Time = "17:00")

$ErrorActionPreference = "Stop"
$ps1 = Join-Path $PSScriptRoot "run_boardroom.ps1"
if (-not (Test-Path $ps1)) { throw "run_boardroom.ps1 not found next to this script." }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ps1`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "Boardroom Daily" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Boardroom autonomous daily checkpoint" -Force | Out-Null

Write-Host "Registered task 'Boardroom Daily' to run daily at $Time (local)."
Write-Host "It launches run_boardroom.ps1 -> one live checkpoint -> logs\scheduler.log."
Write-Host "Manage it in Task Scheduler, or remove with:  Unregister-ScheduledTask -TaskName 'Boardroom Daily' -Confirm:`$false"
