$ErrorActionPreference = "Stop"

Write-Host "Starting TheSNMC RustDB docker stack..." -ForegroundColor Cyan
docker compose up --build
