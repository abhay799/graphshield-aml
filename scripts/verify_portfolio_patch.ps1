$ErrorActionPreference = "Stop"

Write-Host "GraphShield portfolio patch verification" -ForegroundColor Cyan

$required = @(
    "README.md",
    "docs\ARCHITECTURE.md",
    "docs\DEMO_SCRIPT.md",
    "docs\SCREENSHOT_PLAN.md",
    "docs\PROJECT_BOUNDARIES.md",
    "docs\PORTFOLIO_FINALIZATION.md"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing portfolio file: $path"
    }
}

Write-Host "`nPortfolio docs present: PASS" -ForegroundColor Green
Write-Host "`nCurrent branch:" -ForegroundColor Yellow
git branch --show-current

Write-Host "`nWorking tree:" -ForegroundColor Yellow
git status --short

Write-Host "`nDo not use git add ." -ForegroundColor Magenta
