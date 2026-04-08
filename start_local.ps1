$ErrorActionPreference = "Stop"

Write-Host "Starting TheSNMC RustDB local demo API..." -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:8080/admin" -ForegroundColor Green

function Resolve-PythonCommand {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Python was not found. Install Python 3.10+ and re-run .\start_local.ps1"
}

$pythonCommand = Resolve-PythonCommand
$venvDir = ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (!(Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    if ($pythonCommand -eq "py") {
        & py -3 -m venv $venvDir
    } else {
        & python -m venv $venvDir
    }
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "Launching API..." -ForegroundColor Cyan
& $venvPython main.py
