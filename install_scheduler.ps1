# Boardroom — register the TWICE-DAILY checkpoints as a Windows Scheduled Task.
# Run once. Re-run to change the times. Defaults: 09:30 and 15:00 LOCAL — one near
# the open, one ~1 hour before the 4pm-local close. Each checkpoint auto-trades
# crypto (Kraken, 24/7) and refreshes the ADVISORY stock recommendation + the IBKR
# holdings diff. Stocks are never auto-traded, so the times are not fill-critical;
# they're chosen to keep the recommendation fresh through the trading day.
# (The run is launched with --once, so each local trigger time IS an execution
# time; CHECKPOINT_TIMES drives the dashboard countdown.)
#
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1 -Morning 09:30 -Afternoon 15:00
param([string]$Morning = "09:30", [string]$Afternoon = "15:00")

$ErrorActionPreference = "Stop"
# Use the .cmd launcher — Task Scheduler reliably runs batch files, whereas
# PowerShell .ps1 scripts often silently fail to launch from the scheduler.
$cmd = Join-Path $PSScriptRoot "run_boardroom.cmd"
if (-not (Test-Path $cmd)) { throw "run_boardroom.cmd not found next to this script." }

$action = New-ScheduledTaskAction -Execute $cmd -WorkingDirectory $PSScriptRoot
# Two daily triggers on one task — fires a fresh checkpoint at each time.
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At $Morning),
    (New-ScheduledTaskTrigger -Daily -At $Afternoon)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "Boardroom Daily" -Action $action -Trigger $triggers `
    -Settings $settings -Description "Boardroom autonomous twice-daily checkpoints" -Force | Out-Null

Write-Host "Registered task 'Boardroom Daily' to run twice daily at $Morning and $Afternoon (local)."
Write-Host "Each launches run_boardroom.cmd -> one live checkpoint -> logs\scheduler.log."
Write-Host "Manage it in Task Scheduler, or remove with:  Unregister-ScheduledTask -TaskName 'Boardroom Daily' -Confirm:`$false"
