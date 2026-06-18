# start-dev.ps1
# Easy one-command dev server starter for Windows (PowerShell)
# Usage: Right-click -> Run with PowerShell, or in terminal: .\start-dev.ps1

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$venvDir = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  VolstruisGids - Development Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Create venv if it doesn't exist
if (-not (Test-Path $venvPython)) {
    Write-Host "Virtual environment not found. Creating .venv..." -ForegroundColor Yellow
    python -m venv .venv
    if (-not (Test-Path $venvPython)) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        Write-Host "Make sure Python is installed and available as 'python'." -ForegroundColor Red
        exit 1
    }
    Write-Host "Created .venv successfully." -ForegroundColor Green
}

Write-Host "Using Python: $venvPython" -ForegroundColor Green
& $venvPython --version

# Fast check: only run pip install if the package that was failing (requests) is missing
$requestsOk = $false
try {
    $ver = & $venvPython -c "import requests; print(requests.__version__)" 2>&1
    if ($ver -match '^\d') {
        Write-Host "requests already installed: $ver" -ForegroundColor Green
        $requestsOk = $true
    }
} catch {}

if (-not $requestsOk) {
    Write-Host ""
    Write-Host "Core packages missing. Installing from requirements.txt..." -ForegroundColor Yellow
    # --prefer-binary avoids trying to compile Pillow from source on py3.14 Windows
    & $venvPython -m pip install -r requirements.txt --disable-pip-version-check --prefer-binary
    Write-Host ""
}

# One more verification
try {
    & $venvPython -c "import requests, flask; print('All critical imports OK')" 
} catch {
    Write-Host "WARNING: Still having import issues. You may need to recreate the venv." -ForegroundColor Red
}

Write-Host ""
Write-Host "Starting Flask dev server..." -ForegroundColor Green
Write-Host "(Press Ctrl+C to stop)" -ForegroundColor DarkGray
Write-Host ""

# Run the app using the venv python directly (most reliable)
& $venvPython run.py
