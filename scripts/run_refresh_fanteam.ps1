# Wrapper Task Scheduler actually calls - runs refresh_fanteam.py from the
# real project directory and appends timestamped output to logs/, so a
# silent background failure still leaves a real record to check.
$ErrorActionPreference = "Stop"
$root = "C:\Users\info\OneDrive\Documents\OneDrive\Desktop\hailmary-nfl-projections"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "fanteam_refresh.log"
$python = "C:\Users\info\AppData\Local\Python\pythoncore-3.14-64\python.exe"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n===== $timestamp ====="

Set-Location $root
$output = & $python "scripts\refresh_fanteam.py" 2>&1 | Out-String
$exitCode = $LASTEXITCODE

Add-Content -Path $logFile -Value $output -Encoding utf8
Add-Content -Path $logFile -Value "Exit code: $exitCode" -Encoding utf8
exit $exitCode
