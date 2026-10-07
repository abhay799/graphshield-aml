from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api import live_scoring_routes
from api.app import app
from services.live_transaction_scoring_service import LiveTransactionScoringService

REDIS_URL = "redis://127.0.0.1:6379/0"


def _payload(
    *,
    transaction_id: str,
    event_ts: str,
    from_account: str = "MODE_A_SENDER",
    to_account: str = "MODE_A_RECEIVER",
) -> dict:
    return {
        "transaction_id": transaction_id,
        "event_ts": event_ts,
        "from_bank": "MODE_A_BANK_A",
        "from_account": from_account,
        "to_bank": "MODE_A_BANK_B",
        "to_account": to_account,
        "amount_paid": 1000.0,
        "amount_received": 1000.0,
        "payment_currency": "US Dollar",
        "receiving_currency": "US Dollar",
        "payment_format": "ACH",
    }


def _service() -> LiveTransactionScoringService:
    return LiveTransactionScoringService(
        redis_url=REDIS_URL,
        namespace=f"gs:test:mode-a-guard:{uuid4().hex}",
    )


def _client(service: LiveTransactionScoringService) -> TestClient:
    live_scoring_routes.get_live_scoring_service = lambda: service
    return TestClient(app)


def test_mode_a_accepts_forward_moving_transactions_and_advances_watermark():
    service = _service()
    try:
        first = service.score_transaction(
            _payload(
                transaction_id="MODE_A_FORWARD_1",
                event_ts="2026-10-08T00:00:00Z",
            )
        )
        second = service.score_transaction(
            _payload(
                transaction_id="MODE_A_FORWARD_2",
                event_ts="2026-10-08T00:00:01Z",
            )
        )

        assert first["runtime_state_updated"] is True
        assert second["runtime_state_updated"] is True
        assert service.state_writer.watermark_ts() == pytest.approx(1791417601.0)
    finally:
        service.wrapper.clear()


def test_mode_a_rejects_event_older_than_live_frontier_without_mutating_state():
    service = _service()
    try:
        service.score_transaction(
            _payload(
                transaction_id="MODE_A_FRONTIER_BASE",
                event_ts="2026-10-08T00:00:00Z",
            )
        )

        before = service.wrapper.engine.h(
            "sender_hist", "MODE_A_BANK_A::MODE_A_SENDER"
        )

        with pytest.raises(Exception, match="event predates current live state frontier"):
            service.score_transaction(
                _payload(
                    transaction_id="MODE_A_TOO_OLD",
                    event_ts="2026-10-07T23:59:59Z",
                )
            )

        after = service.wrapper.engine.h(
            "sender_hist", "MODE_A_BANK_A::MODE_A_SENDER"
        )
        assert after == before
        assert service.state_writer.watermark_ts() == pytest.approx(1791417600.0)
    finally:
        service.wrapper.clear()


def test_mode_a_rejects_duplicate_transaction_id_without_double_commit():
    service = _service()
    try:
        payload = _payload(
            transaction_id="MODE_A_DUPLICATE",
            event_ts="2026-10-08T00:00:00Z",
        )
        service.score_transaction(payload)

        before = service.wrapper.engine.h(
            "sender_hist", "MODE_A_BANK_A::MODE_A_SENDER"
        )

        with pytest.raises(Exception, match="transaction_id already committed"):
            service.score_transaction(payload)

        after = service.wrapper.engine.h(
            "sender_hist", "MODE_A_BANK_A::MODE_A_SENDER"
        )
        assert after == before
    finally:
        service.wrapper.clear()


def test_mode_a_same_timestamp_group_is_allowed_and_committed_together():
    service = _service()
    try:
        group = [
            _payload(
                transaction_id="MODE_A_GROUP_1",
                event_ts="2026-10-08T00:00:00Z",
                from_account="MODE_A_GROUP_S1",
                to_account="MODE_A_GROUP_R1",
            ),
            _payload(
                transaction_id="MODE_A_GROUP_2",
                event_ts="2026-10-08T00:00:00Z",
                from_account="MODE_A_GROUP_S2",
                to_account="MODE_A_GROUP_R2",
            ),
        ]

        service.state_writer.commit_group(group)

        assert service.state_writer.watermark_ts() == pytest.approx(1791417600.0)
        assert service.state_writer.is_committed("MODE_A_GROUP_1") is True
        assert service.state_writer.is_committed("MODE_A_GROUP_2") is True
    finally:
        service.wrapper.clear()


def test_mode_a_api_surfaces_frontier_and_duplicate_conflicts_as_http_409():
    service = _service()
    client = _client(service)
    try:
        accepted = _payload(
            transaction_id="MODE_A_API_BASE",
            event_ts="2026-10-08T00:00:00Z",
        )
        assert client.post("/score/transaction", json=accepted).status_code == 200

        older = _payload(
            transaction_id="MODE_A_API_OLDER",
            event_ts="2026-10-07T23:59:59Z",
        )
        older_response = client.post("/score/transaction", json=older)
        assert older_response.status_code == 409
        assert "event predates current live state frontier" in older_response.json()["detail"]

        duplicate_response = client.post("/score/transaction", json=accepted)
        assert duplicate_response.status_code == 409
        assert "transaction_id already committed" in duplicate_response.json()["detail"]
    finally:
        service.wrapper.clear()


def test_mode_a_known_unknown_differentiation_survives_forward_only_guard():
    service = _service()
    try:
        cold = service.score_transaction(
            _payload(
                transaction_id="MODE_A_KNOWN_1",
                event_ts="2026-10-08T00:00:00Z",
            )
        )
        warm = service.score_transaction(
            _payload(
                transaction_id="MODE_A_KNOWN_2",
                event_ts="2026-10-08T00:00:01Z",
            )
        )

        assert cold["account_history"] == {
            "sender": "unknown",
            "receiver": "unknown",
        }
        assert cold["limited_signal"] is True

        assert warm["account_history"] == {
            "sender": "known",
            "receiver": "known",
        }
        assert warm["limited_signal"] is False
    finally:
        service.wrapper.clear()


def test_mode_a_rejects_nonempty_legacy_namespace_without_guard_metadata():
    service = _service()
    try:
        # Simulate legacy/bootstrap state written directly through the certified
        # wrapper before Mode A guard metadata existed.
        service.wrapper.commit_group(
            [
                _payload(
                    transaction_id="LEGACY_SEEDED_EVENT",
                    event_ts="2026-10-08T00:00:00Z",
                )
            ]
        )

        assert service.state_writer.watermark_ts() is None

        with pytest.raises(
            Exception,
            match="guard metadata missing for nonempty live namespace",
        ):
            service.score_transaction(
                _payload(
                    transaction_id="MODE_A_AFTER_LEGACY",
                    event_ts="2026-10-08T00:00:01Z",
                )
            )
    finally:
        service.wrapper.clear()
