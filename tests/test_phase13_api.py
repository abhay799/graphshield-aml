import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.phase13_routes as routes


def test_phase13_read_only_observability_endpoints(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "PHASE13_DIR", tmp_path)

    payloads = {
        "governance_status_v1_report.json": {"status": "REVIEW_REQUIRED"},
        "drift_investigation_v1_report.json": {"recommended_next_action": "human_drift_investigation"},
        "performance_monitor_v1_report.json": {"status": "INSUFFICIENT_VALID_LABELS"},
        "retraining_review_proposal_v1_report.json": {"proposal_status": "NOT_READY"},
        "governance_gate_v1_report.json": {"status": "PASS"},
    }
    for name, payload in payloads.items():
        (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")

    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    assert client.get("/phase13/status").status_code == 200
    assert client.get("/phase13/drift").status_code == 200
    assert client.get("/phase13/performance").status_code == 200
    assert client.get("/phase13/retraining-proposal").status_code == 200
    assert client.get("/phase13/governance-gate").status_code == 200


def test_missing_report_fails_closed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(routes, "PHASE13_DIR", tmp_path)
    app = FastAPI()
    app.include_router(routes.router)
    client = TestClient(app)

    response = client.get("/phase13/status")
    assert response.status_code == 503
