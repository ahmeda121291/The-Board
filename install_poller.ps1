# Boardroom — register the "Run now" poller as a Windows Scheduled Task that
# starts at logon and keeps running, so the dashboard's Run button always has a
# listener on this machine. The 3pm daily checkpoint task is separate and stays.
#
#   powershell -ExecutionPolicy Bypass -File .\install_poller.ps1
$ErrorActionPreference = "Stop"
$ps1 = Join-Path $PSScriptRoot "run_poller.ps1"
if (-not (Test-Path $ps1)) { throw "run_poller.ps1 not found next to this script." }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ps1`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
# Keep it alive: restart if it ever stops, no time limit.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName "Boardroom Poller" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Boardroom on-demand Run-now poller" -Force | Out-Null

Write-Host "Registered task 'Boardroom Poller' (starts at logon, runs continuously)." -ForegroundColor Green
Write-Host "It listens for dashboard 'Run now' clicks and executes them locally -> logs\poller.log."
Write-Host "Start it now without logging off:  Start-ScheduledTask -TaskName 'Boardroom Poller'"
Write-Host "Remove with:  Unregister-ScheduledTask -TaskName 'Boardroom Poller' -Confirm:`$false"
