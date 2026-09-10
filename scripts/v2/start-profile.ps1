param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("streaming","mlops","observability","security","graph")]
    [string]$Profile
)

$Compose = "infra\v2\docker-compose.infra.yml"
$EnvFile = "infra\v2\.env"

Write-Host "Starting GraphShield v2 profile: $Profile" -ForegroundColor Cyan

docker compose `
    --env-file $EnvFile `
    -f $Compose `
    --profile $Profile `
    up -d

if ($LASTEXITCODE -ne 0) {
    throw "GraphShield profile startup failed."
}

Write-Host "GRAPHSHIELD_PROFILE_START=PASS" -ForegroundColor Green
