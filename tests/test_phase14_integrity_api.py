from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.phase14_routes as routes


def test_integrity_endpoint_pass(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "verify_artifact_manifest",
        lambda: {
            "status": "PASS",
            "verified": True,
            "mismatches": [],
        },
    )

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get("/deployment/integrity")
    assert response.status_code == 200
    assert response.json()["verified"] is True


def test_integrity_endpoint_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "verify_artifact_manifest",
        lambda: {
            "status": "FAIL",
            "verified": False,
            "mismatches": [
                {
                    "path": "model.bin",
                    "reason": "sha256_mismatch",
                }
            ],
        },
    )

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get("/deployment/integrity")
    assert response.status_code == 503
    assert response.json()["detail"]["verified"] is False
