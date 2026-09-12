from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

try:
    from scipy import sparse
except ImportError as exc:
    raise SystemExit(
        "scipy is required. Install with: python -m pip install scipy"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RISK_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_v1.parquet"
)

PAIR_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "graph_features_v2_pair.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_propagation_v1.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase9"
    / "account_risk_propagation_v1_report.json"
)

VERSION = "account_risk_propagation_v1"


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 9 - Multi-hop Risk Propagation v1")
    print("=" * 88)

    for path in (RISK_PATH, PAIR_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    risk = pl.read_parquet(RISK_PATH).sort("account_key")

    required_risk = {
        "account_key",
        "last_scored_ts",
        "high_risk_txn_count",
        "entity_risk_seed_raw",
        "entity_risk_seed_calibrated",
    }

    missing = required_risk.difference(risk.columns)
    if missing:
        raise RuntimeError(f"Missing account risk columns: {sorted(missing)}")

    if risk["account_key"].n_unique() != risk.height:
        raise RuntimeError("account_risk_v1 contains duplicate account_key values.")

    cutoff = risk.select(pl.col("last_scored_ts").max()).item()

    if cutoff is None:
        raise RuntimeError("No scored timestamp available for propagation cutoff.")

    # graph_features_v2_pair.event_ts is timezone-naive while the risk artifact is UTC.
    # The underlying timestamps represent the same dataset clock, so compare using a
    # timezone-naive copy of the UTC cutoff.
    cutoff_pair = cutoff.replace(tzinfo=None)

    seeds = risk.filter(pl.col("high_risk_txn_count") > 0)

    if seeds.height == 0:
        raise RuntimeError("No high-risk seed accounts found.")

    print(f"ACCOUNT_NODES={risk.height:,}")
    print(f"HIGH_RISK_SEEDS={seeds.height:,}")
    print(f"SNAPSHOT_CUTOFF_UTC={cutoff.isoformat()}")

    # Build one directed pair-strength edge per account pair as of the snapshot.
    #
    # pair_prior_tx_count is point-in-time. For the latest observed transaction on
    # a pair, prior_count + 1 equals the cumulative pair transaction count as of
    # that event. max(prior_count) + 1 therefore gives the pair strength at cutoff.
    #
    # Self-transfers are excluded because they do not propagate exposure to another
    # account.
    pair_state = (
        pl.scan_parquet(PAIR_PATH)
        .select(
            [
                "event_ts",
                "from_account_key",
                "to_account_key",
                "pair_prior_tx_count",
            ]
        )
        .filter(pl.col("event_ts") <= pl.lit(cutoff_pair))
        .filter(pl.col("from_account_key") != pl.col("to_account_key"))
        .group_by(["from_account_key", "to_account_key"])
        .agg(
            pl.col("pair_prior_tx_count")
            .max()
            .alias("max_pair_prior_tx_count")
        )
        .with_columns(
            (
                pl.col("max_pair_prior_tx_count").cast(pl.Float64)
                + 1.0
            ).alias("pair_tx_count")
        )
        .select(
            [
                "from_account_key",
                "to_account_key",
                "pair_tx_count",
            ]
        )
        .collect(engine="streaming")
    )

    if pair_state.height == 0:
        raise RuntimeError("No pair edges available at propagation cutoff.")

    print(f"DIRECTED_PAIR_EDGES={pair_state.height:,}")

    # Row-normalize outgoing pair strength. This makes every source account
    # distribute its current exposure across counterparties according to the
    # observed transaction-frequency strength of each directed relationship.
    outgoing_totals = (
        pair_state.group_by("from_account_key")
        .agg(
            pl.col("pair_tx_count")
            .sum()
            .alias("source_pair_tx_total")
        )
    )

    pair_state = (
        pair_state.join(
            outgoing_totals,
            on="from_account_key",
            how="left",
        )
        .with_columns(
            (
                pl.col("pair_tx_count")
                / pl.col("source_pair_tx_total")
            ).alias("transition_weight")
        )
    )

    weight_check = (
        pair_state.group_by("from_account_key")
        .agg(pl.col("transition_weight").sum().alias("weight_sum"))
    )

    min_weight_sum = float(weight_check["weight_sum"].min())
    max_weight_sum = float(weight_check["weight_sum"].max())

    if not np.isclose(min_weight_sum, 1.0, atol=1e-9):
        raise RuntimeError(
            f"Outgoing transition weights do not sum to 1. min={min_weight_sum}"
        )

    if not np.isclose(max_weight_sum, 1.0, atol=1e-9):
        raise RuntimeError(
            f"Outgoing transition weights do not sum to 1. max={max_weight_sum}"
        )

    node_index = risk.select("account_key").with_row_index("node_idx")

    indexed_pairs = (
        pair_state.join(
            node_index.rename(
                {
                    "account_key": "from_account_key",
                    "node_idx": "src_idx",
                }
            ),
            on="from_account_key",
            how="left",
        )
        .join(
            node_index.rename(
                {
                    "account_key": "to_account_key",
                    "node_idx": "dst_idx",
                }
            ),
            on="to_account_key",
            how="left",
        )
    )

    if indexed_pairs["src_idx"].null_count() > 0:
        raise RuntimeError("Pair graph contains an unknown source account.")

    if indexed_pairs["dst_idx"].null_count() > 0:
        raise RuntimeError("Pair graph contains an unknown destination account.")

    n_nodes = risk.height

    src_idx = indexed_pairs["src_idx"].to_numpy().astype(np.int64, copy=False)
    dst_idx = indexed_pairs["dst_idx"].to_numpy().astype(np.int64, copy=False)
    weights = indexed_pairs["transition_weight"].to_numpy().astype(
        np.float64, copy=False
    )

    transition = sparse.csr_matrix(
        (weights, (src_idx, dst_idx)),
        shape=(n_nodes, n_nodes),
        dtype=np.float64,
    )

    seed_mask = (
        risk["high_risk_txn_count"].to_numpy() > 0
    )

    seed_raw = np.where(
        seed_mask,
        risk["entity_risk_seed_raw"].to_numpy(),
        0.0,
    ).astype(np.float64, copy=False)

    seed_cal = np.where(
        seed_mask,
        risk["entity_risk_seed_calibrated"].to_numpy(),
        0.0,
    ).astype(np.float64, copy=False)

    # Separate hop outputs are retained deliberately. We do not invent a learned
    # probability or arbitrary decay formula. Each hop is directly interpretable
    # as transaction-frequency-weighted exposure from the previous hop.
    hop1_raw = transition.T.dot(seed_raw)
    hop2_raw = transition.T.dot(hop1_raw)
    hop3_raw = transition.T.dot(hop2_raw)

    hop1_cal = transition.T.dot(seed_cal)
    hop2_cal = transition.T.dot(hop1_cal)
    hop3_cal = transition.T.dot(hop2_cal)

    for name, arr in {
        "hop1_raw": hop1_raw,
        "hop2_raw": hop2_raw,
        "hop3_raw": hop3_raw,
        "hop1_cal": hop1_cal,
        "hop2_cal": hop2_cal,
        "hop3_cal": hop3_cal,
    }.items():
        if not np.all(np.isfinite(arr)):
            raise RuntimeError(f"{name} contains non-finite values.")
        if np.any(arr < -1e-12):
            raise RuntimeError(f"{name} contains negative exposure.")

    shortest_hop = np.full(n_nodes, -1, dtype=np.int8)
    shortest_hop[hop3_raw > 0] = 3
    shortest_hop[hop2_raw > 0] = 2
    shortest_hop[hop1_raw > 0] = 1
    shortest_hop[seed_mask] = 0

    max_hop_raw = np.maximum.reduce([hop1_raw, hop2_raw, hop3_raw])
    cumulative_raw = hop1_raw + hop2_raw + hop3_raw

    output = risk.select(
        [
            "account_key",
            "bank_id",
            "scored_txn_count",
            "high_risk_txn_count",
            "entity_risk_seed_raw",
            "entity_risk_seed_calibrated",
        ]
    ).with_columns(
        [
            pl.Series("hop1_exposure_raw", hop1_raw),
            pl.Series("hop2_exposure_raw", hop2_raw),
            pl.Series("hop3_exposure_raw", hop3_raw),
            pl.Series("hop1_exposure_calibrated", hop1_cal),
            pl.Series("hop2_exposure_calibrated", hop2_cal),
            pl.Series("hop3_exposure_calibrated", hop3_cal),
            pl.Series("max_3hop_exposure_raw", max_hop_raw),
            pl.Series("cumulative_3hop_exposure_raw", cumulative_raw),
            pl.Series("shortest_hop_from_seed", shortest_hop),
            pl.lit(cutoff).alias("propagation_snapshot_ts"),
            pl.lit(VERSION).alias("propagation_version"),
            pl.lit(
                "pair_prior_tx_count_max_plus_one_row_normalized"
            ).alias("edge_weight_definition"),
            pl.lit(
                "separate_hops_no_decay_no_probability_claim"
            ).alias("propagation_semantics"),
        ]
    )

    reachable_nonseed = output.filter(
        (pl.col("shortest_hop_from_seed") > 0)
    ).height

    hop1_accounts = output.filter(
        pl.col("hop1_exposure_raw") > 0
    ).height

    hop2_accounts = output.filter(
        pl.col("hop2_exposure_raw") > 0
    ).height

    hop3_accounts = output.filter(
        pl.col("hop3_exposure_raw") > 0
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
        "step": "4A",
        "version": VERSION,
        "labels_used": False,
        "snapshot_cutoff_utc": cutoff.isoformat(),
        "account_nodes": n_nodes,
        "high_risk_seed_accounts": seeds.height,
        "directed_pair_edges": pair_state.height,
        "self_transfers_excluded": True,
        "edge_weight_definition": (
            "max(pair_prior_tx_count)+1 per directed pair, "
            "row-normalized by source"
        ),
        "propagation_direction": "transaction flow: sender -> receiver",
        "propagation_hops": 3,
        "decay_applied": False,
        "probability_claim": False,
        "outgoing_weight_sum_min": min_weight_sum,
        "outgoing_weight_sum_max": max_weight_sum,
        "hop1_reached_accounts": hop1_accounts,
        "hop2_reached_accounts": hop2_accounts,
        "hop3_reached_accounts": hop3_accounts,
        "reachable_nonseed_accounts": reachable_nonseed,
        "output": str(OUTPUT_PATH.relative_to(PROJECT_ROOT)),
        "risk_source": str(RISK_PATH.relative_to(PROJECT_ROOT)),
        "pair_feature_source": str(PAIR_PATH.relative_to(PROJECT_ROOT)),
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"HOP1_REACHED_ACCOUNTS={hop1_accounts:,}")
    print(f"HOP2_REACHED_ACCOUNTS={hop2_accounts:,}")
    print(f"HOP3_REACHED_ACCOUNTS={hop3_accounts:,}")
    print(f"REACHABLE_NONSEED_ACCOUNTS={reachable_nonseed:,}")
    print(f"OUTGOING_WEIGHT_SUM_MIN={min_weight_sum:.12f}")
    print(f"OUTGOING_WEIGHT_SUM_MAX={max_weight_sum:.12f}")
    print(f"OUTPUT={OUTPUT_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print("DECAY_APPLIED=FALSE")
    print("PROBABILITY_CLAIM=FALSE")
    print("LABEL_LEAKAGE=NONE")
    print("GRAPHSHIELD_PHASE9_STEP4A=PASS")


if __name__ == "__main__":
    main()
