from __future__ import annotations

import json
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PREDICTIONS_PATH = PROJECT_ROOT / "data" / "processed" / "modeling" / "champion_test_predictions.parquet"
EDGES_PATH = PROJECT_ROOT / "data" / "processed" / "graph" / "transaction_edges.parquet"
NODES_PATH = PROJECT_ROOT / "data" / "processed" / "graph" / "account_nodes.parquet"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "graph" / "account_risk_v1.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "v2" / "phase9" / "account_risk_v1_report.json"


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 9 - Account Risk Aggregation v1")
    print("=" * 88)

    for path in (PREDICTIONS_PATH, EDGES_PATH, NODES_PATH):
        require_file(path)

    # Labels are intentionally excluded from the aggregation.
    predictions = pl.read_parquet(
        PREDICTIONS_PATH,
        columns=["transaction_id", "risk_score_raw", "risk_score_calibrated"],
    )

    prediction_rows = predictions.height
    prediction_unique_ids = predictions["transaction_id"].n_unique()

    if prediction_rows == 0:
        raise RuntimeError("Champion prediction file is empty.")

    if prediction_unique_ids != prediction_rows:
        raise RuntimeError("Champion predictions contain duplicate transaction_id values.")

    joined = (
        pl.scan_parquet(EDGES_PATH)
        .select(["transaction_id", "event_ts", "from_account_key", "to_account_key"])
        .join(predictions.lazy(), on="transaction_id", how="inner")
        .collect(engine="streaming")
    )

    joined_rows = joined.height
    joined_unique_ids = joined["transaction_id"].n_unique()

    if joined_rows != prediction_rows:
        raise RuntimeError(
            f"Champion-to-edge join mismatch: predictions={prediction_rows:,}, "
            f"joined={joined_rows:,}. Refusing incomplete risk state."
        )

    if joined_unique_ids != prediction_rows:
        raise RuntimeError("Joined graph edges are not one-to-one by transaction_id.")

    high_risk_threshold_raw = float(
        joined.select(
            pl.col("risk_score_raw").quantile(0.99, interpolation="nearest")
        ).item()
    )

    joined = joined.with_columns(
        (pl.col("risk_score_raw") >= pl.lit(high_risk_threshold_raw))
        .cast(pl.UInt8)
        .alias("is_high_risk_score")
    )

    outbound = joined.select(
        [
            pl.col("from_account_key").alias("account_key"),
            "transaction_id",
            "event_ts",
            "risk_score_raw",
            "risk_score_calibrated",
            "is_high_risk_score",
        ]
    )

    inbound = joined.select(
        [
            pl.col("to_account_key").alias("account_key"),
            "transaction_id",
            "event_ts",
            "risk_score_raw",
            "risk_score_calibrated",
            "is_high_risk_score",
        ]
    )

    outbound_agg = outbound.group_by("account_key").agg(
        [
            pl.len().cast(pl.UInt32).alias("outbound_scored_txn_count"),
            pl.col("risk_score_raw").mean().alias("outbound_risk_mean_raw"),
            pl.col("risk_score_calibrated").mean().alias("outbound_risk_mean_calibrated"),
            pl.col("risk_score_raw").max().alias("outbound_risk_max_raw"),
        ]
    )

    inbound_agg = inbound.group_by("account_key").agg(
        [
            pl.len().cast(pl.UInt32).alias("inbound_scored_txn_count"),
            pl.col("risk_score_raw").mean().alias("inbound_risk_mean_raw"),
            pl.col("risk_score_calibrated").mean().alias("inbound_risk_mean_calibrated"),
            pl.col("risk_score_raw").max().alias("inbound_risk_max_raw"),
        ]
    )

    account_tx = (
        pl.concat([outbound, inbound], how="vertical")
        .unique(subset=["account_key", "transaction_id"], keep="first")
    )

    overall_agg = (
        account_tx.group_by("account_key")
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("scored_txn_count"),
                pl.col("risk_score_raw").mean().alias("mean_risk_raw"),
                pl.col("risk_score_raw")
                .quantile(0.95, interpolation="nearest")
                .alias("p95_risk_raw"),
                pl.col("risk_score_raw").max().alias("max_risk_raw"),
                pl.col("risk_score_calibrated").mean().alias("mean_risk_calibrated"),
                pl.col("risk_score_calibrated")
                .quantile(0.95, interpolation="nearest")
                .alias("p95_risk_calibrated"),
                pl.col("risk_score_calibrated").max().alias("max_risk_calibrated"),
                pl.col("risk_score_calibrated")
                .sum()
                .alias("risk_exposure_sum_calibrated"),
                pl.col("is_high_risk_score")
                .sum()
                .cast(pl.UInt32)
                .alias("high_risk_txn_count"),
                pl.col("event_ts").min().alias("first_scored_ts"),
                pl.col("event_ts").max().alias("last_scored_ts"),
            ]
        )
        .with_columns(
            (
                pl.col("high_risk_txn_count") / pl.col("scored_txn_count")
            ).alias("high_risk_txn_rate")
        )
    )

    nodes = pl.read_parquet(NODES_PATH)

    risk = (
        nodes.join(overall_agg, on="account_key", how="left")
        .join(outbound_agg, on="account_key", how="left")
        .join(inbound_agg, on="account_key", how="left")
    )

    numeric_zero_cols = [
        "scored_txn_count",
        "mean_risk_raw",
        "p95_risk_raw",
        "max_risk_raw",
        "mean_risk_calibrated",
        "p95_risk_calibrated",
        "max_risk_calibrated",
        "risk_exposure_sum_calibrated",
        "high_risk_txn_count",
        "high_risk_txn_rate",
        "outbound_scored_txn_count",
        "outbound_risk_mean_raw",
        "outbound_risk_mean_calibrated",
        "outbound_risk_max_raw",
        "inbound_scored_txn_count",
        "inbound_risk_mean_raw",
        "inbound_risk_mean_calibrated",
        "inbound_risk_max_raw",
    ]

    provenance = {
        "phase": "9",
        "artifact": "account_risk_v1",
        "prediction_source": str(PREDICTIONS_PATH.relative_to(PROJECT_ROOT)),
        "edge_source": str(EDGES_PATH.relative_to(PROJECT_ROOT)),
        "node_source": str(NODES_PATH.relative_to(PROJECT_ROOT)),
        "labels_used_for_risk_aggregation": False,
        "high_risk_threshold_rule": (
            "99th percentile of champion raw transaction risk within the available "
            "scored champion test subset"
        ),
        "entity_risk_seed_definition": (
            "maximum champion transaction risk touching the account"
        ),
        "scope_note": (
            "v1 account risk is based only on transactions present in "
            "champion_test_predictions.parquet; it is not a full-history account probability."
        ),
    }

    risk = (
        risk.with_columns([pl.col(c).fill_null(0) for c in numeric_zero_cols])
        .with_columns(
            [
                pl.col("max_risk_raw").alias("entity_risk_seed_raw"),
                pl.col("max_risk_calibrated").alias("entity_risk_seed_calibrated"),
                pl.lit(high_risk_threshold_raw).alias("high_risk_threshold_raw"),
                pl.lit("available_champion_test_predictions").alias("risk_scope"),
                pl.lit(json.dumps(provenance, sort_keys=True)).alias("provenance"),
            ]
        )
        .sort(
            ["entity_risk_seed_raw", "scored_txn_count"],
            descending=[True, True],
        )
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    risk.write_parquet(OUTPUT_PATH, compression="zstd")

    scored_accounts = int(risk.filter(pl.col("scored_txn_count") > 0).height)
    high_risk_accounts = int(risk.filter(pl.col("high_risk_txn_count") > 0).height)

    report = {
        "status": "PASS",
        "prediction_rows": prediction_rows,
        "prediction_unique_ids": prediction_unique_ids,
        "joined_rows": joined_rows,
        "joined_unique_ids": joined_unique_ids,
        "account_nodes": risk.height,
        "scored_accounts": scored_accounts,
        "high_risk_accounts": high_risk_accounts,
        "high_risk_threshold_raw": high_risk_threshold_raw,
        "labels_used_for_risk_aggregation": False,
        "output": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "provenance": provenance,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"PREDICTIONS={prediction_rows:,}")
    print(f"JOINED={joined_rows:,}")
    print(f"ACCOUNT_NODES={risk.height:,}")
    print(f"SCORED_ACCOUNTS={scored_accounts:,}")
    print(f"HIGH_RISK_ACCOUNTS={high_risk_accounts:,}")
    print(f"HIGH_RISK_THRESHOLD_RAW={high_risk_threshold_raw:.12f}")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_LEAKAGE=NONE")
    print("GRAPHSHIELD_PHASE9_ACCOUNT_RISK=PASS")


if __name__ == "__main__":
    main()
