from __future__ import annotations

import json
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MOTIF_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v5_motifs.parquet"
)

RISK_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_v1.parquet"
)

PROPAGATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_propagation_v1.parquet"
)

COMMUNITY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "suspicious_community_membership_v1.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_motif_intelligence_v1.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase9"
    / "account_motif_intelligence_v1_report.json"
)

VERSION = "account_motif_intelligence_v1"


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 9 - Account Motif Intelligence v1")
    print("=" * 88)

    for path in (
        MOTIF_PATH,
        RISK_PATH,
        PROPAGATION_PATH,
        COMMUNITY_PATH,
    ):
        if not path.exists():
            raise FileNotFoundError(path)

    risk = pl.read_parquet(RISK_PATH)

    if risk["account_key"].n_unique() != risk.height:
        raise RuntimeError("account_risk_v1 contains duplicate account_key values.")

    cutoff = risk.select(pl.col("last_scored_ts").max()).item()

    if cutoff is None:
        raise RuntimeError("No scored timestamp available for motif snapshot cutoff.")

    # graph_features_v5_motifs.event_ts is timezone-naive. Its timestamps represent
    # the same source clock as the UTC risk artifact, so use a timezone-naive copy
    # only for the comparison.
    cutoff_naive = cutoff.replace(tzinfo=None)

    print(f"ACCOUNT_NODES={risk.height:,}")
    print(f"SNAPSHOT_CUTOFF_UTC={cutoff.isoformat()}")

    # Ground-truth is deliberately not selected.
    motif_scan = (
        pl.scan_parquet(MOTIF_PATH)
        .select(
            [
                "transaction_id",
                "event_ts",
                "from_account_key",
                "to_account_key",
                "sender_fanout_ratio_1h",
                "sender_fanout_ratio_24h",
                "receiver_fanin_ratio_1h",
                "receiver_fanin_ratio_24h",
                "rapid_pass_through_candidate",
                "closes_two_node_cycle",
            ]
        )
        .filter(pl.col("event_ts") <= pl.lit(cutoff_naive))
    )

    motif_rows = motif_scan.select(pl.len()).collect().item()

    print(f"SNAPSHOT_TRANSACTIONS={motif_rows:,}")

    sender = (
        motif_scan.group_by("from_account_key")
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("sender_snapshot_tx_count"),
                pl.col("rapid_pass_through_candidate")
                .sum()
                .cast(pl.UInt32)
                .alias("rapid_pass_through_tx_count"),
                pl.col("sender_fanout_ratio_1h")
                .max()
                .alias("max_sender_fanout_ratio_1h"),
                pl.col("sender_fanout_ratio_24h")
                .max()
                .alias("max_sender_fanout_ratio_24h"),
                pl.col("sender_fanout_ratio_1h")
                .mean()
                .alias("mean_sender_fanout_ratio_1h"),
                pl.col("sender_fanout_ratio_24h")
                .mean()
                .alias("mean_sender_fanout_ratio_24h"),
            ]
        )
        .rename({"from_account_key": "account_key"})
        .collect(engine="streaming")
    )

    receiver = (
        motif_scan.group_by("to_account_key")
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("receiver_snapshot_tx_count"),
                pl.col("receiver_fanin_ratio_1h")
                .max()
                .alias("max_receiver_fanin_ratio_1h"),
                pl.col("receiver_fanin_ratio_24h")
                .max()
                .alias("max_receiver_fanin_ratio_24h"),
                pl.col("receiver_fanin_ratio_1h")
                .mean()
                .alias("mean_receiver_fanin_ratio_1h"),
                pl.col("receiver_fanin_ratio_24h")
                .mean()
                .alias("mean_receiver_fanin_ratio_24h"),
            ]
        )
        .rename({"to_account_key": "account_key"})
        .collect(engine="streaming")
    )

    # A two-node cycle-closing transaction is relevant to both endpoints.
    cycle_edges = (
        motif_scan.filter(pl.col("closes_two_node_cycle") > 0)
        .select(
            [
                "transaction_id",
                "from_account_key",
                "to_account_key",
            ]
        )
        .collect(engine="streaming")
    )

    if cycle_edges.height:
        cycle_accounts = (
            pl.concat(
                [
                    cycle_edges.select(
                        [
                            "transaction_id",
                            pl.col("from_account_key").alias("account_key"),
                        ]
                    ),
                    cycle_edges.select(
                        [
                            "transaction_id",
                            pl.col("to_account_key").alias("account_key"),
                        ]
                    ),
                ],
                how="vertical",
            )
            .unique(
                subset=["account_key", "transaction_id"],
                keep="first",
            )
            .group_by("account_key")
            .agg(
                pl.len()
                .cast(pl.UInt32)
                .alias("two_node_cycle_close_tx_count")
            )
        )
    else:
        cycle_accounts = pl.DataFrame(
            schema={
                "account_key": pl.String,
                "two_node_cycle_close_tx_count": pl.UInt32,
            }
        )

    propagation = pl.read_parquet(
        PROPAGATION_PATH,
        columns=[
            "account_key",
            "shortest_hop_from_seed",
            "max_3hop_exposure_raw",
            "cumulative_3hop_exposure_raw",
            "propagation_version",
        ],
    )

    if propagation["account_key"].n_unique() != propagation.height:
        raise RuntimeError(
            "account_risk_propagation_v1 contains duplicate account_key values."
        )

    community = pl.read_parquet(
        COMMUNITY_PATH,
        columns=[
            "account_key",
            "community_id",
            "is_high_risk_seed",
        ],
    )

    if community["account_key"].n_unique() != community.height:
        raise RuntimeError(
            "suspicious community membership contains duplicate account_key values."
        )

    zero_fill = [
        "sender_snapshot_tx_count",
        "rapid_pass_through_tx_count",
        "receiver_snapshot_tx_count",
        "two_node_cycle_close_tx_count",
        "max_sender_fanout_ratio_1h",
        "max_sender_fanout_ratio_24h",
        "mean_sender_fanout_ratio_1h",
        "mean_sender_fanout_ratio_24h",
        "max_receiver_fanin_ratio_1h",
        "max_receiver_fanin_ratio_24h",
        "mean_receiver_fanin_ratio_1h",
        "mean_receiver_fanin_ratio_24h",
    ]

    output = (
        risk.select(
            [
                "account_key",
                "bank_id",
                "scored_txn_count",
                "high_risk_txn_count",
                "entity_risk_seed_raw",
                "entity_risk_seed_calibrated",
            ]
        )
        .join(sender, on="account_key", how="left")
        .join(receiver, on="account_key", how="left")
        .join(cycle_accounts, on="account_key", how="left")
        .join(propagation, on="account_key", how="left")
        .join(community, on="account_key", how="left")
        .with_columns([pl.col(c).fill_null(0) for c in zero_fill])
        .with_columns(
            [
                (pl.col("rapid_pass_through_tx_count") > 0)
                .alias("has_rapid_pass_through_signal"),
                (pl.col("two_node_cycle_close_tx_count") > 0)
                .alias("has_two_node_cycle_signal"),
                (
                    (pl.col("rapid_pass_through_tx_count") > 0)
                    | (pl.col("two_node_cycle_close_tx_count") > 0)
                ).alias("has_any_motif_signal"),
                (pl.col("high_risk_txn_count") > 0)
                .alias("is_high_risk_seed_account"),
                pl.col("community_id")
                .is_not_null()
                .alias("is_in_suspicious_community"),
                pl.lit(cutoff).alias("motif_snapshot_ts"),
                pl.lit(VERSION).alias("motif_version"),
                pl.lit(False).alias("label_used_for_motif_intelligence"),
            ]
        )
    )

    if output["account_key"].n_unique() != risk.height:
        raise RuntimeError("Final motif output is not one row per account.")

    if output.height != risk.height:
        raise RuntimeError(
            f"Account coverage mismatch: {output.height:,} != {risk.height:,}"
        )

    rapid_accounts = output.filter(
        pl.col("has_rapid_pass_through_signal")
    ).height

    cycle_accounts_count = output.filter(
        pl.col("has_two_node_cycle_signal")
    ).height

    any_motif_accounts = output.filter(
        pl.col("has_any_motif_signal")
    ).height

    high_risk_with_motif = output.filter(
        pl.col("is_high_risk_seed_account")
        & pl.col("has_any_motif_signal")
    ).height

    community_with_motif = output.filter(
        pl.col("is_in_suspicious_community")
        & pl.col("has_any_motif_signal")
    ).height

    propagated_with_motif = output.filter(
        (pl.col("shortest_hop_from_seed") > 0)
        & pl.col("has_any_motif_signal")
    ).height

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    output.write_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "5A",
        "version": VERSION,
        "labels_used": False,
        "snapshot_cutoff_utc": cutoff.isoformat(),
        "snapshot_transactions": motif_rows,
        "account_nodes": output.height,
        "rapid_pass_through_accounts": rapid_accounts,
        "two_node_cycle_accounts": cycle_accounts_count,
        "accounts_with_any_motif_signal": any_motif_accounts,
        "high_risk_seed_accounts_with_motif": high_risk_with_motif,
        "suspicious_community_accounts_with_motif": community_with_motif,
        "propagated_nonseed_accounts_with_motif": propagated_with_motif,
        "motif_signals": [
            "rapid_pass_through_candidate",
            "closes_two_node_cycle",
            "sender_fanout_ratio_1h",
            "sender_fanout_ratio_24h",
            "receiver_fanin_ratio_1h",
            "receiver_fanin_ratio_24h",
        ],
        "risk_context_joined": True,
        "community_context_joined": True,
        "propagation_context_joined": True,
        "composite_probability_created": False,
        "output": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"RAPID_PASS_THROUGH_ACCOUNTS={rapid_accounts:,}")
    print(f"TWO_NODE_CYCLE_ACCOUNTS={cycle_accounts_count:,}")
    print(f"ANY_MOTIF_ACCOUNTS={any_motif_accounts:,}")
    print(f"HIGH_RISK_SEEDS_WITH_MOTIF={high_risk_with_motif:,}")
    print(f"COMMUNITY_ACCOUNTS_WITH_MOTIF={community_with_motif:,}")
    print(f"PROPAGATED_NONSEED_WITH_MOTIF={propagated_with_motif:,}")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print("COMPOSITE_PROBABILITY_CREATED=FALSE")
    print("LABEL_LEAKAGE=NONE")
    print("GRAPHSHIELD_PHASE9_STEP5A=PASS")


if __name__ == "__main__":
    main()
