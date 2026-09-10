$ErrorActionPreference="Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
Write-Host "Stopping GraphShield AML..." -ForegroundColor Cyan
docker compose down
Write-Host "GraphShield AML stopped." -ForegroundColor Green
