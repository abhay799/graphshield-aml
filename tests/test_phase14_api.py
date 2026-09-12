from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.phase14_routes as routes
from enterprise.phase14_runtime import (
    Phase14RuntimeConfig,
    install_enterprise_security,
)


def _config(
    *,
    strict: bool,
    required_paths: tuple[str, ...] = (),
) -> Phase14RuntimeConfig:
    return Phase14RuntimeConfig(
        environment="test",
        release="phase14-test",
        commit_sha="abc123",
        region="test-region",
        instance_id="pod-1",
        strict_readiness=strict,
        enable_hsts=False,
        required_paths=required_paths,
    )


def test_live_and_deployment_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_runtime_config",
        lambda: _config(strict=False),
    )

    app = FastAPI()
    app.include_router(routes.router)
    install_enterprise_security(app)
    client = TestClient(app)

    live = client.get("/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    deployment = client.get("/deployment")
    assert deployment.status_code == 200
    body = deployment.json()
    assert body["phase"] == 14
    assert body["safety_boundary"]["human_review_required"] is True
    assert body["safety_boundary"]["autonomous_account_blocking"] is False

    assert live.headers["Permissions-Policy"] == (
        "camera=(), microphone=(), geolocation=()"
    )


def test_ready_fails_closed_when_artifacts_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "get_runtime_config",
        lambda: _config(
            strict=True,
            required_paths=("definitely-missing.file",),
        ),
    )

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["detail"]["ready"] is False
