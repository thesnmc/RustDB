$ErrorActionPreference = "Stop"

Write-Host "Starting TheSNMC RustDB local demo API..." -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:8080/admin" -ForegroundColor Green
python main.py
