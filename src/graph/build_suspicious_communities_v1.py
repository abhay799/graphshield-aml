from __future__ import annotations

import json
import math
from pathlib import Path

import networkx as nx
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RISK_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_v1.parquet"
)

EDGES_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "transaction_edges.parquet"
)

MEMBERSHIP_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "suspicious_community_membership_v1.parquet"
)

SUMMARY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "suspicious_communities_v1.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase9"
    / "suspicious_communities_v1_report.json"
)

SEED = 42
RESOLUTION = 1.0


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 9 - Suspicious Community Detection v1")
    print("=" * 88)

    if not RISK_PATH.exists():
        raise FileNotFoundError(RISK_PATH)
    if not EDGES_PATH.exists():
        raise FileNotFoundError(EDGES_PATH)

    risk = pl.read_parquet(RISK_PATH)

    required_risk_cols = {
        "account_key",
        "scored_txn_count",
        "high_risk_txn_count",
        "entity_risk_seed_raw",
        "entity_risk_seed_calibrated",
        "risk_exposure_sum_calibrated",
    }
    missing = required_risk_cols.difference(risk.columns)
    if missing:
        raise RuntimeError(f"Missing risk columns: {sorted(missing)}")

    seeds = risk.filter(pl.col("high_risk_txn_count") > 0).select("account_key")
    seed_ids = set(seeds["account_key"].to_list())

    if not seed_ids:
        raise RuntimeError("No high-risk seed accounts found.")

    print(f"HIGH_RISK_SEEDS={len(seed_ids):,}")

    # 1-hop expansion from the label-free high-risk seed set.
    one_hop_edges = (
        pl.scan_parquet(EDGES_PATH)
        .select(
            [
                "transaction_id",
                "from_account_key",
                "to_account_key",
                "amount_paid",
            ]
        )
        .filter(
            pl.col("from_account_key").is_in(seed_ids)
            | pl.col("to_account_key").is_in(seed_ids)
        )
        .collect(engine="streaming")
    )

    candidate_nodes = set(seed_ids)
    candidate_nodes.update(one_hop_edges["from_account_key"].to_list())
    candidate_nodes.update(one_hop_edges["to_account_key"].to_list())

    print(f"ONE_HOP_TRANSACTIONS={one_hop_edges.height:,}")
    print(f"CANDIDATE_ACCOUNTS={len(candidate_nodes):,}")

    # Build the induced graph on the seed + 1-hop candidate node set.
    # This captures transactions among neighboring accounts as well, not only
    # the transactions directly touching a seed.
    induced = (
        pl.scan_parquet(EDGES_PATH)
        .select(
            [
                "transaction_id",
                "from_account_key",
                "to_account_key",
                "amount_paid",
            ]
        )
        .filter(
            pl.col("from_account_key").is_in(candidate_nodes)
            & pl.col("to_account_key").is_in(candidate_nodes)
        )
        .collect(engine="streaming")
    )

    if induced.height == 0:
        raise RuntimeError("Induced suspicious-community graph is empty.")

    print(f"INDUCED_TRANSACTIONS={induced.height:,}")

    # Convert directed multiedges into deterministic undirected weighted pairs.
    # Louvain weight = transaction count only. Amount is retained for reporting
    # but is not mixed into the community objective with an arbitrary formula.
    weighted_pairs = (
        induced.with_columns(
            [
                pl.when(pl.col("from_account_key") <= pl.col("to_account_key"))
                .then(pl.col("from_account_key"))
                .otherwise(pl.col("to_account_key"))
                .alias("u"),
                pl.when(pl.col("from_account_key") <= pl.col("to_account_key"))
                .then(pl.col("to_account_key"))
                .otherwise(pl.col("from_account_key"))
                .alias("v"),
            ]
        )
        .group_by(["u", "v"])
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("transaction_count"),
                pl.col("amount_paid").sum().alias("total_amount_paid"),
            ]
        )
    )

    graph = nx.Graph()
    graph.add_nodes_from(candidate_nodes)

    for row in weighted_pairs.iter_rows(named=True):
        graph.add_edge(
            row["u"],
            row["v"],
            weight=float(row["transaction_count"]),
            transaction_count=int(row["transaction_count"]),
            total_amount_paid=float(row["total_amount_paid"]),
        )

    communities = nx.algorithms.community.louvain_communities(
        graph,
        weight="weight",
        resolution=RESOLUTION,
        seed=SEED,
    )

    # Stable community IDs: larger communities first, then lexical minimum node.
    communities = sorted(
        communities,
        key=lambda c: (-len(c), min(c)),
    )

    membership_rows: list[dict] = []
    for idx, members in enumerate(communities, start=1):
        community_id = f"SCV1_{idx:06d}"
        for account_key in sorted(members):
            membership_rows.append(
                {
                    "account_key": account_key,
                    "community_id": community_id,
                }
            )

    membership = pl.DataFrame(membership_rows)

    enriched_membership = (
        membership.join(
            risk.select(
                [
                    "account_key",
                    "scored_txn_count",
                    "high_risk_txn_count",
                    "entity_risk_seed_raw",
                    "entity_risk_seed_calibrated",
                    "risk_exposure_sum_calibrated",
                ]
            ),
            on="account_key",
            how="left",
        )
        .with_columns(
            [
                pl.col("scored_txn_count").fill_null(0),
                pl.col("high_risk_txn_count").fill_null(0),
                pl.col("entity_risk_seed_raw").fill_null(0.0),
                pl.col("entity_risk_seed_calibrated").fill_null(0.0),
                pl.col("risk_exposure_sum_calibrated").fill_null(0.0),
                pl.col("account_key").is_in(seed_ids).alias("is_high_risk_seed"),
            ]
        )
    )

    edge_membership = (
        induced.join(
            membership.rename(
                {
                    "account_key": "from_account_key",
                    "community_id": "from_community_id",
                }
            ),
            on="from_account_key",
            how="left",
        )
        .join(
            membership.rename(
                {
                    "account_key": "to_account_key",
                    "community_id": "to_community_id",
                }
            ),
            on="to_account_key",
            how="left",
        )
        .filter(pl.col("from_community_id") == pl.col("to_community_id"))
    )

    internal_stats = (
        edge_membership.group_by("from_community_id")
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("internal_transaction_count"),
                pl.col("amount_paid").sum().alias("internal_amount_paid"),
            ]
        )
        .rename({"from_community_id": "community_id"})
    )

    summary = (
        enriched_membership.group_by("community_id")
        .agg(
            [
                pl.len().cast(pl.UInt32).alias("member_count"),
                pl.col("is_high_risk_seed")
                .sum()
                .cast(pl.UInt32)
                .alias("high_risk_seed_count"),
                (pl.col("scored_txn_count") > 0)
                .sum()
                .cast(pl.UInt32)
                .alias("scored_account_count"),
                pl.col("entity_risk_seed_raw")
                .max()
                .alias("max_entity_risk_seed_raw"),
                pl.col("entity_risk_seed_calibrated")
                .max()
                .alias("max_entity_risk_seed_calibrated"),
                pl.col("entity_risk_seed_raw")
                .mean()
                .alias("mean_entity_risk_seed_raw"),
                pl.col("risk_exposure_sum_calibrated")
                .sum()
                .alias("risk_exposure_sum_calibrated"),
            ]
        )
        .join(internal_stats, on="community_id", how="left")
        .with_columns(
            [
                pl.col("internal_transaction_count").fill_null(0),
                pl.col("internal_amount_paid").fill_null(0.0),
            ]
        )
        # Transparent lexicographic priority, not an arbitrary blended score.
        .sort(
            [
                "high_risk_seed_count",
                "max_entity_risk_seed_raw",
                "member_count",
                "internal_transaction_count",
            ],
            descending=[True, True, True, True],
        )
        .with_row_index("community_priority_rank", offset=1)
    )

    high_risk_communities = summary.filter(
        pl.col("high_risk_seed_count") > 0
    ).height

    if high_risk_communities == 0:
        raise RuntimeError("No detected community contains a high-risk seed.")

    if enriched_membership["account_key"].n_unique() != len(candidate_nodes):
        raise RuntimeError("Community membership is not one-to-one by account.")

    MEMBERSHIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    enriched_membership.write_parquet(
        MEMBERSHIP_PATH,
        compression="zstd",
    )
    summary.write_parquet(
        SUMMARY_PATH,
        compression="zstd",
    )

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "3A",
        "algorithm": "Louvain",
        "networkx_version": nx.__version__,
        "seed": SEED,
        "resolution": RESOLUTION,
        "labels_used": False,
        "seed_definition": "account_risk_v1.high_risk_txn_count > 0",
        "expansion": "exact 1-hop seed neighborhood, then induced subgraph",
        "community_weight": "aggregated transaction_count",
        "priority_rule": (
            "lexicographic sort by high_risk_seed_count, "
            "max_entity_risk_seed_raw, member_count, "
            "internal_transaction_count"
        ),
        "high_risk_seed_accounts": len(seed_ids),
        "one_hop_transactions": one_hop_edges.height,
        "candidate_accounts": len(candidate_nodes),
        "induced_transactions": induced.height,
        "weighted_pairs": weighted_pairs.height,
        "communities": summary.height,
        "communities_with_high_risk_seed": high_risk_communities,
        "membership_output": str(
            MEMBERSHIP_PATH.relative_to(PROJECT_ROOT)
        ),
        "summary_output": str(
            SUMMARY_PATH.relative_to(PROJECT_ROOT)
        ),
    }

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"COMMUNITIES={summary.height:,}")
    print(
        "COMMUNITIES_WITH_HIGH_RISK_SEED="
        f"{high_risk_communities:,}"
    )
    print(f"MEMBERSHIP_ROWS={enriched_membership.height:,}")
    print(f"WEIGHTED_PAIRS={weighted_pairs.height:,}")
    print(f"MEMBERSHIP_OUTPUT={MEMBERSHIP_PATH}")
    print(f"SUMMARY_OUTPUT={SUMMARY_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_LEAKAGE=NONE")
    print("GRAPHSHIELD_PHASE9_STEP3A=PASS")


if __name__ == "__main__":
    main()
