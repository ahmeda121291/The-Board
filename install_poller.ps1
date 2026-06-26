# Boardroom — register the "Run now" poller as a Windows Scheduled Task that
# starts at logon and keeps running, so the dashboard's Run button always has a
# listener on this machine. The 3pm daily checkpoint task is separate and stays.
#
#   powershell -ExecutionPolicy Bypass -File .\install_poller.ps1
$ErrorActionPreference = "Stop"
$ps1 = Join-Path $PSScriptRoot "run_poller.ps1"
if (-not (Test-Path $ps1)) { throw "run_poller.ps1 not found next to this script." }

$me = "$env:USERDOMAIN\$env:USERNAME"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ps1`""
# AtLogOn scoped to THIS user (an unscoped 'any user' trigger needs admin).
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
# Run as the current user, limited rights — no elevation required.
$principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
# Keep it alive: restart if it ever stops, no time limit.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

try {
    Register-ScheduledTask -TaskName "Boardroom Poller" -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description "Boardroom on-demand Run-now poller" -Force | Out-Null
}
catch {
    Write-Host "Could not register the task: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "If this is 'Access is denied', right-click PowerShell -> 'Run as administrator'," -ForegroundColor Yellow
    Write-Host "cd back to this folder, and re-run this script. Or skip the task entirely and just" -ForegroundColor Yellow
    Write-Host "run the poller in a window when you need it:  python -m boardroom.cli poll --confirm-live" -ForegroundColor Yellow
    exit 1
}

Write-Host "Registered task 'Boardroom Poller' (starts at logon, runs continuously)." -ForegroundColor Green
Write-Host "It listens for dashboard 'Run now' clicks and executes them locally -> logs\poller.log."
Write-Host "Start it now without logging off:  Start-ScheduledTask -TaskName 'Boardroom Poller'"
Write-Host "Remove with:  Unregister-ScheduledTask -TaskName 'Boardroom Poller' -Confirm:`$false"
