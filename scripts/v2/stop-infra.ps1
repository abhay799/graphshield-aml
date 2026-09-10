$containers = @(
    "graphshield-redis",
    "graphshield-redpanda",
    "graphshield-minio",
    "graphshield-mlflow",
    "graphshield-prometheus",
    "graphshield-grafana",
    "graphshield-keycloak",
    "graphshield-neo4j"
)

foreach ($name in $containers) {
    $running = docker ps -q -f "name=^${name}$"

    if ($running) {
        docker stop $name | Out-Null
        Write-Host "Stopped $name"
    }
}

Write-Host "GRAPHSHIELD_INFRA_STOP=PASS" -ForegroundColor Green
