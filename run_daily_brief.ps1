# run_daily_brief.ps1
# Wrapper script for Windows Task Scheduler to run the Second Brain nightly process.
# Place this in the project root: d:\ai second brain\files\

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $ProjectRoot "data\logs"
$LogFile = Join-Path $LogDir ("brief_" + (Get-Date -Format "yyyy-MM-dd") + ".log")

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Start Ollama server if not already running
$ollamaRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/" -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) { $ollamaRunning = $true }
} catch {}

if (-not $ollamaRunning) {
    Write-Output "[$(Get-Date -Format 'HH:mm:ss')] Starting Ollama server..." | Tee-Object -FilePath $LogFile -Append
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 8  # Give Ollama time to load
}

# Run the nightly orchestration script
Write-Output "[$(Get-Date -Format 'HH:mm:ss')] Starting Second Brain nightly run..." | Tee-Object -FilePath $LogFile -Append

$PythonExe = Join-Path $ProjectRoot "venv\Scripts\python.exe"
$Script    = Join-Path $ProjectRoot "src\daily_brief.py"

& $PythonExe $Script 2>&1 | Tee-Object -FilePath $LogFile -Append

Write-Output "[$(Get-Date -Format 'HH:mm:ss')] Nightly run complete. Log saved to: $LogFile" | Tee-Object -FilePath $LogFile -Append
