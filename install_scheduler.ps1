# Boardroom — register the daily checkpoints as a Windows Scheduled Task.
# Run once. Re-run to change the times. Default: FOUR checkpoints across the
# trading day (09:30, 11:30, 13:30, 15:00 LOCAL) — more frequent so crypto
# (Kraken, 24/7, auto-traded) gets more shots while the account is small, and the
# advisory stock recommendation + IBKR holdings diff stay fresh through the day.
# Stocks are never auto-traded, so the exact times aren't fill-critical.
# (Each run is launched with --once, so every local trigger time IS an execution
# time; CHECKPOINT_TIMES drives the dashboard countdown.)
#
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1
#   powershell -ExecutionPolicy Bypass -File .\install_scheduler.ps1 -Times "09:30,12:30,15:00"
param([string]$Times = "09:30,11:30,13:30,15:00")

$ErrorActionPreference = "Stop"
# Use the .cmd launcher — Task Scheduler reliably runs batch files, whereas
# PowerShell .ps1 scripts often silently fail to launch from the scheduler.
$cmd = Join-Path $PSScriptRoot "run_boardroom.cmd"
if (-not (Test-Path $cmd)) { throw "run_boardroom.cmd not found next to this script." }

$timeList = $Times.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
if ($timeList.Count -eq 0) { throw "No valid times in -Times '$Times'." }

$action = New-ScheduledTaskAction -Execute $cmd -WorkingDirectory $PSScriptRoot
# One daily trigger per time on a single task — fires a fresh checkpoint at each.
$triggers = @($timeList | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName "Boardroom Daily" -Action $action -Trigger $triggers `
    -Settings $settings -Description "Boardroom autonomous checkpoints (multiple daily)" -Force | Out-Null

Write-Host "Registered task 'Boardroom Daily' to run at $($timeList -join ', ') (local) every day."
Write-Host "Each launches run_boardroom.cmd -> one live checkpoint -> logs\scheduler.log."
Write-Host "Manage it in Task Scheduler, or remove with:  Unregister-ScheduledTask -TaskName 'Boardroom Daily' -Confirm:`$false"
