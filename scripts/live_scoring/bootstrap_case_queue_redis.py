from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl

RAW_COLUMNS = [
    "transaction_id",
    "source_row_number",
    "event_ts",
    "from_bank",
    "from_account",
    "to_bank",
    "to_account",
    "amount_paid",
    "amount_received",
    "payment_currency",
    "receiving_currency",
    "payment_format",
]


@dataclass(frozen=True)
class BootstrapScope:
    case_count: int
    account_keys: set[str]
    cutoff_event_ts: datetime
    verification_transaction_id: str


def _with_account_keys(frame: pl.DataFrame | pl.LazyFrame):
    return frame.with_columns(
        [
            pl.concat_str(
                [pl.col("from_bank").cast(pl.String), pl.col("from_account").cast(pl.String)],
                separator="::",
            ).alias("_from_account_key"),
            pl.concat_str(
                [pl.col("to_bank").cast(pl.String), pl.col("to_account").cast(pl.String)],
                separator="::",
            ).alias("_to_account_key"),
        ]
    )


def derive_case_scope(case_queue: pl.DataFrame, transactions: pl.DataFrame) -> BootstrapScope:
    case_ids = case_queue.select("transaction_id").unique()
    targets = (
        case_ids.join(transactions, on="transaction_id", how="inner")
        .pipe(_with_account_keys)
        .sort(["event_ts", "transaction_id"])
    )
    if targets.height != case_ids.height:
        raise RuntimeError(
            f"Case target lookup incomplete: expected {case_ids.height}, found {targets.height}."
        )
    if targets.is_empty():
        raise RuntimeError("Case queue contains no target transactions.")
    account_keys = set(targets["_from_account_key"].to_list())
    account_keys.update(targets["_to_account_key"].to_list())
    latest = targets.row(-1, named=True)
    return BootstrapScope(
        case_count=case_ids.height,
        account_keys=account_keys,
        cutoff_event_ts=latest["event_ts"],
        verification_transaction_id=str(latest["transaction_id"]),
    )


def filter_case_scoped_history(
    transactions: pl.DataFrame,
    *,
    account_keys: set[str],
    cutoff_event_ts: datetime,
) -> pl.DataFrame:
    keyed = _with_account_keys(transactions)
    sort_columns = ["event_ts"]
    if "source_row_number" in keyed.collect_schema().names():
        sort_columns.append("source_row_number")
    sort_columns.append("transaction_id")
    return (
        keyed.filter(
            (pl.col("event_ts") < pl.lit(cutoff_event_ts))
            & (
                pl.col("_from_account_key").is_in(account_keys)
                | pl.col("_to_account_key").is_in(account_keys)
            )
        )
        .drop(["_from_account_key", "_to_account_key"])
        .sort(sort_columns)
    )


def build_plan(
    case_queue_path: Path,
    transactions_path: Path,
) -> tuple[BootstrapScope, pl.LazyFrame, int, int]:
    case_queue = pl.read_parquet(case_queue_path, columns=["transaction_id"])
    case_ids = case_queue["transaction_id"].unique().to_list()
    targets = (
        pl.scan_parquet(transactions_path)
        .filter(pl.col("transaction_id").is_in(case_ids))
        .select(
            [
                "transaction_id",
                "event_ts",
                "from_bank",
                "from_account",
                "to_bank",
                "to_account",
            ]
        )
        .collect(engine="streaming")
    )
    scope = derive_case_scope(case_queue, targets)
    history = _with_account_keys(
        pl.scan_parquet(transactions_path).select(RAW_COLUMNS)
    ).filter(
        (pl.col("event_ts") < pl.lit(scope.cutoff_event_ts))
        & (
            pl.col("_from_account_key").is_in(scope.account_keys)
            | pl.col("_to_account_key").is_in(scope.account_keys)
        )
    ).drop(["_from_account_key", "_to_account_key"])
    selected_rows = int(
        history.select(pl.len().alias("n")).collect(engine="streaming")["n"][0]
    )
    source_rows = int(
        pl.scan_parquet(transactions_path)
        .select(pl.len().alias("n"))
        .collect(engine="streaming")["n"][0]
    )
    return scope, history, selected_rows, source_rows


class _TransportChunkedPipeline:
    """Replay queued Redis commands through bounded transport-sized pipelines.

    The certified Engine builds one transactional pipeline per commit_group().
    During bootstrap only, large timestamp groups can expand into thousands of
    Redis commands and exceed the Railway socket write timeout. This proxy keeps
    command order unchanged but executes the queued commands in smaller
    transactions. Bootstrap never computes features between these sub-batches,
    so the final state remains equivalent before advancing to the next timestamp.
    """

    def __init__(
        self,
        *,
        pipeline_factory,
        transaction: bool,
        max_commands: int,
    ) -> None:
        if max_commands < 1:
            raise ValueError("max_commands must be >= 1")
        self._pipeline_factory = pipeline_factory
        self._transaction = transaction
        self._max_commands = max_commands
        self._commands: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def queue(*args, **kwargs):
            self._commands.append((name, args, kwargs))
            return self

        return queue

    def execute(self):
        results = []
        for start in range(0, len(self._commands), self._max_commands):
            pipe = self._pipeline_factory(transaction=self._transaction)
            for name, args, kwargs in self._commands[
                start : start + self._max_commands
            ]:
                getattr(pipe, name)(*args, **kwargs)
            results.extend(pipe.execute())
        self._commands.clear()
        return results


def chunk_timestamp_group(
    group: list[dict],
    *,
    max_batch_rows: int,
):
    """Yield ordered commit batches without crossing timestamp boundaries."""
    if max_batch_rows < 1:
        raise ValueError("max_batch_rows must be >= 1")
    for start in range(0, len(group), max_batch_rows):
        yield group[start : start + max_batch_rows]


def replay_history(
    history: pl.DataFrame,
    *,
    redis_url: str,
    namespace: str,
    max_seconds: int,
    max_pipeline_rows: int = 500,
    max_pipeline_commands: int = 1000,
) -> dict[str, int | float | str]:
    from src.services.live_scoring_feature_wrapper import FrozenModelFeatureWrapper

    wrapper = FrozenModelFeatureWrapper(redis_url, namespace)
    original_pipeline_factory = wrapper.engine.r.pipeline
    wrapper.engine.r.pipeline = lambda transaction=True, shard_hint=None: (
        _TransportChunkedPipeline(
            pipeline_factory=original_pipeline_factory,
            transaction=transaction,
            max_commands=max_pipeline_commands,
        )
    )
    started = time.monotonic()
    groups = 0
    rows = 0
    commit_batches = 0
    chunked_groups = 0
    max_group_rows = 0
    records = history.sort(
        ["event_ts", "source_row_number", "transaction_id"]
    ).to_dicts()
    for _, iterator in groupby(records, key=lambda row: row["event_ts"]):
        elapsed = time.monotonic() - started
        if elapsed > max_seconds:
            raise TimeoutError(
                f"Bootstrap exceeded {max_seconds}s after {rows} rows / {groups} groups."
            )
        group = list(iterator)
        max_group_rows = max(max_group_rows, len(group))
        batches = list(
            chunk_timestamp_group(
                group,
                max_batch_rows=max_pipeline_rows,
            )
        )
        if len(batches) > 1:
            chunked_groups += 1
        for batch in batches:
            wrapper.commit_group(batch)
            commit_batches += 1
        rows += len(group)
        groups += 1
        if groups % 500 == 0:
            print(
                f"BOOTSTRAP_PROGRESS rows={rows} groups={groups} "
                f"elapsed_seconds={time.monotonic() - started:.1f}",
                flush=True,
            )
    return {
        "rows_replayed": rows,
        "timestamp_groups": groups,
        "commit_batches": commit_batches,
        "chunked_groups": chunked_groups,
        "max_group_rows": max_group_rows,
        "max_pipeline_rows": max_pipeline_rows,
        "max_pipeline_commands": max_pipeline_commands,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "namespace": namespace,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-queue", default="data/processed/cases/case_queue.parquet")
    parser.add_argument("--transactions", default="data/processed/silver/transactions.parquet")
    parser.add_argument("--redis-url", default=None)
    parser.add_argument(
        "--namespace",
        default=os.getenv("GS_LIVE_SCORING_NAMESPACE", "gs:live:scoring:v1"),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-seconds", type=int, default=900)
    parser.add_argument("--max-history-rows", type=int, default=750000)
    parser.add_argument("--max-pipeline-rows", type=int, default=500)
    parser.add_argument("--max-pipeline-commands", type=int, default=1000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scope, history_lf, selected_rows, source_rows = build_plan(
        Path(args.case_queue), Path(args.transactions)
    )
    plan = {
        "case_count": scope.case_count,
        "unique_case_accounts": len(scope.account_keys),
        "selected_history_rows": selected_rows,
        "source_transaction_rows": source_rows,
        "selected_fraction": selected_rows / source_rows if source_rows else 0.0,
        "cutoff_event_ts": str(scope.cutoff_event_ts),
        "verification_transaction_id": scope.verification_transaction_id,
        "namespace": args.namespace,
    }
    print("BOOTSTRAP_PLAN=" + json.dumps(plan, sort_keys=True), flush=True)
    if args.dry_run:
        return 0
    if selected_rows > args.max_history_rows:
        print(
            f"BOOTSTRAP_STOP=ROW_LIMIT selected={selected_rows} "
            f"limit={args.max_history_rows}",
            flush=True,
        )
        return 2

    redis_url = (
        args.redis_url
        or os.getenv("GS_LIVE_SCORING_REDIS_URL")
        or os.getenv("REDIS_URL")
    )
    if not redis_url:
        raise RuntimeError("Redis URL required.")

    history = (
        history_lf.sort(["event_ts", "source_row_number", "transaction_id"])
        .collect(engine="streaming")
    )
    result = replay_history(
        history,
        redis_url=redis_url,
        namespace=args.namespace,
        max_seconds=args.max_seconds,
        max_pipeline_rows=args.max_pipeline_rows,
        max_pipeline_commands=args.max_pipeline_commands,
    )
    print("BOOTSTRAP_RESULT=" + json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
