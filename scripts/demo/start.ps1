$ErrorActionPreference="Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..\..")
Write-Host "Starting GraphShield AML..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "Waiting for API..."
for ($i=1; $i -le 12; $i++) {
    Start-Sleep -Seconds 5
    try {
        $h=Invoke-RestMethod "http://127.0.0.1:8000/health"
        if ($h.status -eq "ok") { break }
    } catch {}
}
Write-Host "GraphShield AML is ready." -ForegroundColor Green
Write-Host "Workbench: http://127.0.0.1:8501"
Write-Host "API Docs:  http://127.0.0.1:8000/docs"
Write-Host "Metrics:   http://127.0.0.1:8000/metrics"
