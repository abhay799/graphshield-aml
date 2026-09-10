param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("streaming","mlops","observability","security","graph")]
    [string]$Profile
)

$Profiles = @{
    streaming     = @("graphshield-redis","graphshield-redpanda")
    mlops         = @("graphshield-minio","graphshield-mlflow")
    observability = @("graphshield-prometheus","graphshield-grafana")
    security      = @("graphshield-keycloak")
    graph         = @("graphshield-neo4j")
}

$failed = $false

foreach ($name in $Profiles[$Profile]) {
    $status = docker inspect --format '{{.State.Status}}' $name 2>$null

    if ($LASTEXITCODE -ne 0 -or $status -ne "running") {
        Write-Host "$name -> NOT RUNNING" -ForegroundColor Red
        $failed = $true
        continue
    }

    $health = docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' $name 2>$null

    if ($health -eq "unhealthy") {
        Write-Host "$name -> UNHEALTHY" -ForegroundColor Red
        $failed = $true
    }
    elseif ($health -eq "healthy") {
        Write-Host "$name -> RUNNING / HEALTHY" -ForegroundColor Green
    }
    else {
        Write-Host "$name -> RUNNING" -ForegroundColor Green
    }
}

if ($failed) {
    throw "GRAPHSHIELD_PROFILE_HEALTH=FAIL"
}

Write-Host "GRAPHSHIELD_PROFILE_HEALTH=PASS" -ForegroundColor Green
