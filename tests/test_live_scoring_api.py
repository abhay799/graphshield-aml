from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from api import live_scoring_routes
from api.app import app
from services.live_transaction_scoring_service import LiveTransactionScoringService


REDIS_URL = "redis://127.0.0.1:6379/0"


def _client_with_service(service: LiveTransactionScoringService) -> TestClient:
    live_scoring_routes.get_live_scoring_service = lambda: service
    return TestClient(app)


def test_live_score_unknown_accounts_returns_limited_signal_and_score():
    service = LiveTransactionScoringService(
        redis_url=REDIS_URL,
        namespace=f"gs:test:live-unknown:{uuid4().hex}",
    )
    request = {
        "transaction_id": "TEST_UNKNOWN_001",
        "event_ts": "2026-10-05T12:00:00Z",
        "from_bank": "TEST_NEW_BANK_A",
        "from_account": "TEST_NEW_SENDER_001",
        "to_bank": "TEST_NEW_BANK_B",
        "to_account": "TEST_NEW_RECEIVER_001",
        "amount_paid": 1000.0,
        "amount_received": 1000.0,
        "payment_currency": "US Dollar",
        "receiving_currency": "US Dollar",
        "payment_format": "ACH",
    }

    client = _client_with_service(service)
    response = client.post("/score/transaction", json=request)

    assert response.status_code == 200
    payload = response.json()
    print("UNKNOWN_RESPONSE=", payload)

    assert 0.0 <= payload["calibrated_score"] <= 1.0
    assert 0.0 <= payload["raw_model_score"] <= 1.0
    assert payload["account_history"] == {
        "sender": "unknown",
        "receiver": "unknown",
    }
    assert payload["limited_signal"] is True
    assert isinstance(payload["limitation_note"], str)
    assert payload["limitation_note"].startswith("Structurally limited signal:")
    assert "first-time accounts" in payload["limitation_note"]
    assert payload["scoring_mode"] == "live_research_only"
    assert payload["boundary"] == "synthetic_research_demo_only"
    assert "not real fraud detection" in payload["boundary_note"].lower()
    assert payload["canonical_artifacts_modified"] is False
    assert payload["runtime_state_updated"] is True
    assert "feature_breakdown" in payload
    assert sum(len(group) for group in payload["feature_breakdown"].values()) == 70
    assert set(payload["feature_breakdown"]) == {
        "transaction", "history", "network", "pass_through"
    }
    assert payload["feature_breakdown"]["history"]["sender_prior_tx_count"] == 0
    assert payload["feature_breakdown"]["network"]["graph_new_pair"] == 1
