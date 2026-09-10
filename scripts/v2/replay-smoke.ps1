$ErrorActionPreference = "Stop"

$Python = ".\.venv\Scripts\python.exe"
$MainConfig = "configs\v2\streaming\replay.yaml"
$TempConfig = "data\phase7\v2_replay_smoke.yaml"
$Checkpoint = "data\phase7\v2_replay_checkpoint.json"
$SmokeTopic = "graphshield.transactions.smoke.v1"

$hadCheckpoint = Test-Path $Checkpoint
$oldCheckpoint = $null

if ($hadCheckpoint) {
    $oldCheckpoint = Get-Content $Checkpoint -Raw
}

try {
    .\scripts\v2\health-profile.ps1 -Profile streaming

    docker exec graphshield-redpanda rpk topic delete $SmokeTopic 2>$null | Out-Null
    docker exec graphshield-redpanda rpk topic create $SmokeTopic --partitions 3 --replicas 1 | Out-Null

    New-Item -ItemType Directory -Force data\phase7 | Out-Null

    (Get-Content $MainConfig) `
        -replace '^topic:.*$', "topic: $SmokeTopic" |
        Set-Content $TempConfig

    Remove-Item $Checkpoint -ErrorAction SilentlyContinue

    & $Python scripts\v2\replay_transactions.py `
        --config $TempConfig `
        --mode burst `
        --max-events 10

    if ($LASTEXITCODE -ne 0) {
        throw "Replay execution failed"
    }

    Write-Host "GRAPHSHIELD_REPLAY_SMOKE=PASS" -ForegroundColor Green
}
finally {
    Remove-Item $TempConfig -ErrorAction SilentlyContinue

    if ($hadCheckpoint) {
        [IO.File]::WriteAllText(
            (Join-Path (Get-Location) $Checkpoint),
            $oldCheckpoint
        )
    }
    else {
        Remove-Item $Checkpoint -ErrorAction SilentlyContinue
    }

    docker exec graphshield-redpanda rpk topic delete $SmokeTopic 2>$null | Out-Null
}
