from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _forward_request(transaction_id: str, event_ts: datetime, amount: float = 100.0) -> dict:
    return {
        "transaction_id": transaction_id,
        "event_ts": _iso(event_ts),
        "from_bank": "TEST_FORWARD_BANK_A",
        "from_account": "TEST_FORWARD_SENDER",
        "to_bank": "TEST_FORWARD_BANK_B",
        "to_account": "TEST_FORWARD_RECEIVER",
        "amount_paid": amount,
        "amount_received": amount,
        "payment_currency": "US Dollar",
        "receiving_currency": "US Dollar",
        "payment_format": "ACH",
    }


def test_live_score_known_accounts_uses_full_history_and_changes_score():
    service = LiveTransactionScoringService(
        redis_url=REDIS_URL,
        namespace=f"gs:test:live-forward:{uuid4().hex}",
    )
    client = _client_with_service(service)
    now = datetime.now(UTC).replace(microsecond=0)

    first = client.post(
        "/score/transaction",
        json=_forward_request("TEST_FORWARD_001", now, 100.0),
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["account_history"] == {"sender": "unknown", "receiver": "unknown"}
    assert first_payload["limited_signal"] is True

    second = client.post(
        "/score/transaction",
        json=_forward_request("TEST_FORWARD_002", now + timedelta(seconds=1), 125.0),
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["account_history"] == {"sender": "known", "receiver": "known"}
    assert second_payload["limited_signal"] is False
    assert second_payload["feature_breakdown"]["history"]["sender_prior_tx_count"] == 1
    assert second_payload["feature_breakdown"]["history"]["receiver_prior_tx_count"] == 1
    assert (
        second_payload["raw_model_score"] != first_payload["raw_model_score"]
        or second_payload["calibrated_score"] != first_payload["calibrated_score"]
    )


def test_future_timestamp_over_five_minutes_is_rejected_before_redis_write():
    namespace = f"gs:test:future-reject:{uuid4().hex}"
    service = LiveTransactionScoringService(redis_url=REDIS_URL, namespace=namespace)
    client = _client_with_service(service)
    redis = service.state_writer.redis

    assert list(redis.scan_iter(match=f"{namespace}:*")) == []
    response = client.post(
        "/score/transaction",
        json=_forward_request(
            "TEST_FUTURE_001",
            datetime.now(UTC) + timedelta(minutes=10),
        ),
    )

    assert response.status_code == 422
    assert "more than 5 minutes ahead of server UTC time" in response.json()["detail"]
    assert list(redis.scan_iter(match=f"{namespace}:*")) == []


def test_normal_current_timestamp_still_scores_after_future_guard():
    namespace = f"gs:test:future-normal:{uuid4().hex}"
    service = LiveTransactionScoringService(redis_url=REDIS_URL, namespace=namespace)
    client = _client_with_service(service)

    response = client.post(
        "/score/transaction",
        json=_forward_request("TEST_CURRENT_001", datetime.now(UTC)),
    )

    assert response.status_code == 200
    assert response.json()["runtime_state_updated"] is True
    assert list(service.state_writer.redis.scan_iter(match=f"{namespace}:*"))
