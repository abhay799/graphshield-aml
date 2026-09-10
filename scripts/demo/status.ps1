Set-Location (Resolve-Path "$PSScriptRoot\..\..")
Write-Host "=== GraphShield AML Demo Status ===" -ForegroundColor Cyan
docker compose ps
try {
    $h=Invoke-RestMethod "http://127.0.0.1:8000/health"
    Write-Host "API:" $h.status
    Write-Host "Champion:" $h.champion
    Write-Host "Case Queue:" $h.case_queue_rows
} catch {
    Write-Host "API: unavailable" -ForegroundColor Red
}
try {
    $u=Invoke-WebRequest "http://127.0.0.1:8501/_stcore/health" -UseBasicParsing
    Write-Host "Workbench HTTP:" $u.StatusCode
} catch {
    Write-Host "Workbench: unavailable" -ForegroundColor Red
}
