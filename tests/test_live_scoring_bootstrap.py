from __future__ import annotations

from datetime import datetime, timezone

import polars as pl

from scripts.live_scoring.bootstrap_case_queue_redis import (
    derive_case_scope,
    filter_case_scoped_history,
)


def _dt(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def test_case_scope_bootstrap_excludes_unrelated_and_cutoff_or_future_rows():
    case_queue = pl.DataFrame(
        {
            "transaction_id": ["CASE_TX_1", "CASE_TX_2"],
        }
    )
    transactions = pl.DataFrame(
        {
            "transaction_id": [
                "HIST_TO_A",
                "HIST_FROM_B",
                "UNRELATED",
                "CASE_TX_1",
                "CASE_TX_2",
                "FUTURE_FROM_C",
            ],
            "event_ts": [_dt(1), _dt(2), _dt(2), _dt(3), _dt(4), _dt(5)],
            "from_bank": ["X", "B1", "X", "B1", "B2", "B2"],
            "from_account": ["X1", "B", "X2", "A", "C", "C"],
            "to_bank": ["B1", "Y", "Y", "B1", "B2", "Z"],
            "to_account": ["A", "Y1", "Y2", "B", "D", "Z1"],
        }
    )

    scope = derive_case_scope(case_queue, transactions)

    assert scope.case_count == 2
    assert scope.account_keys == {"B1::A", "B1::B", "B2::C", "B2::D"}
    assert scope.cutoff_event_ts == _dt(4)
    assert scope.verification_transaction_id == "CASE_TX_2"

    history = filter_case_scoped_history(
        transactions,
        account_keys=scope.account_keys,
        cutoff_event_ts=scope.cutoff_event_ts,
    )

    assert history["transaction_id"].to_list() == [
        "HIST_TO_A",
        "HIST_FROM_B",
        "CASE_TX_1",
    ]


def test_transport_chunked_pipeline_preserves_command_order():
    from scripts.live_scoring.bootstrap_case_queue_redis import _TransportChunkedPipeline

    executed_batches = []

    class FakePipeline:
        def __init__(self):
            self.commands = []

        def __getattr__(self, name):
            def record(*args, **kwargs):
                self.commands.append((name, args, kwargs))
                return self
            return record

        def execute(self):
            executed_batches.append(list(self.commands))
            return [True] * len(self.commands)

    def factory(*, transaction=True):
        assert transaction is True
        return FakePipeline()

    proxy = _TransportChunkedPipeline(
        pipeline_factory=factory,
        transaction=True,
        max_commands=3,
    )

    for index in range(8):
        proxy.zadd(f"k{index}", {f"m{index}": float(index)})

    results = proxy.execute()

    assert [len(batch) for batch in executed_batches] == [3, 3, 2]
    assert [command[1][0] for batch in executed_batches for command in batch] == [
        f"k{index}" for index in range(8)
    ]
    assert results == [True] * 8
