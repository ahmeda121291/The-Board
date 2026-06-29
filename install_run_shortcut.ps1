# Boardroom — create a "Run Boardroom Now" shortcut on your Desktop.
# Double-click it any time to fire one live checkpoint immediately.
#
#   powershell -ExecutionPolicy Bypass -File .\install_run_shortcut.ps1
$ErrorActionPreference = "Stop"

$target = Join-Path $PSScriptRoot "run_now.cmd"
if (-not (Test-Path $target)) { throw "run_now.cmd not found next to this script." }

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "Run Boardroom Now.lnk"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $target
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.IconLocation = "cmd.exe,0"
$lnk.Description = "Run one Boardroom checkpoint now (live)"
$lnk.Save()

Write-Host "Created shortcut: $lnkPath" -ForegroundColor Green
Write-Host "Double-click 'Run Boardroom Now' on your Desktop to fire a checkpoint immediately."
