from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import polars as pl
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
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
    / "neo4j_risk_propagation_v1_report.json"
)

DEFAULT_ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"

VERSION = "account_risk_propagation_v1"

LOAD_COLUMNS = [
    "account_key",
    "hop1_exposure_raw",
    "hop2_exposure_raw",
    "hop3_exposure_raw",
    "hop1_exposure_calibrated",
    "hop2_exposure_calibrated",
    "hop3_exposure_calibrated",
    "max_3hop_exposure_raw",
    "cumulative_3hop_exposure_raw",
    "shortest_hop_from_seed",
    "propagation_snapshot_ts",
    "propagation_version",
    "edge_weight_definition",
    "propagation_semantics",
]


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def resolve_connection() -> tuple[str, str, str]:
    file_env = parse_dotenv(DEFAULT_ENV_PATH)

    def get(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name) or file_env.get(name)
            if value:
                return value
        return None

    uri = (
        get("NEO4J_URI", "GRAPHSHIELD_NEO4J_URI")
        or "bolt://127.0.0.1:7687"
    )

    username = get(
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "GRAPHSHIELD_NEO4J_USER",
    )

    password = get(
        "NEO4J_PASSWORD",
        "GRAPHSHIELD_NEO4J_PASSWORD",
    )

    auth = get("NEO4J_AUTH")

    if auth and "/" in auth:
        auth_user, auth_password = auth.split("/", 1)
        username = username or auth_user
        password = password or auth_password

    username = username or "neo4j"

    if not password:
        raise RuntimeError(
            "Neo4j password not found. Expected NEO4J_PASSWORD, "
            "GRAPHSHIELD_NEO4J_PASSWORD, or NEO4J_AUTH=user/password."
        )

    return uri, username, password


def normalize_rows(batch: pl.DataFrame) -> list[dict]:
    rows: list[dict] = []

    for row in batch.select(LOAD_COLUMNS).iter_rows(named=True):
        snapshot = row["propagation_snapshot_ts"]

        rows.append(
            {
                "account_key": row["account_key"],
                "hop1_exposure_raw": float(row["hop1_exposure_raw"]),
                "hop2_exposure_raw": float(row["hop2_exposure_raw"]),
                "hop3_exposure_raw": float(row["hop3_exposure_raw"]),
                "hop1_exposure_calibrated": float(
                    row["hop1_exposure_calibrated"]
                ),
                "hop2_exposure_calibrated": float(
                    row["hop2_exposure_calibrated"]
                ),
                "hop3_exposure_calibrated": float(
                    row["hop3_exposure_calibrated"]
                ),
                "max_3hop_exposure_raw": float(
                    row["max_3hop_exposure_raw"]
                ),
                "cumulative_3hop_exposure_raw": float(
                    row["cumulative_3hop_exposure_raw"]
                ),
                "shortest_hop_from_seed": int(
                    row["shortest_hop_from_seed"]
                ),
                "propagation_snapshot_ts": snapshot.isoformat(),
                "propagation_version": row["propagation_version"],
                "edge_weight_definition": row["edge_weight_definition"],
                "propagation_semantics": row["propagation_semantics"],
            }
        )

    return rows


def write_batch(tx, rows: list[dict]) -> int:
    record = tx.run(
        """
        UNWIND $rows AS row

        MATCH (a:Account {
            account_id: row.account_key
        })

        SET
            a.propagation_version = row.propagation_version,
            a.propagation_snapshot_ts = datetime(row.propagation_snapshot_ts),
            a.propagation_edge_weight_definition = row.edge_weight_definition,
            a.propagation_semantics = row.propagation_semantics,
            a.hop1_exposure_raw = row.hop1_exposure_raw,
            a.hop2_exposure_raw = row.hop2_exposure_raw,
            a.hop3_exposure_raw = row.hop3_exposure_raw,
            a.hop1_exposure_calibrated = row.hop1_exposure_calibrated,
            a.hop2_exposure_calibrated = row.hop2_exposure_calibrated,
            a.hop3_exposure_calibrated = row.hop3_exposure_calibrated,
            a.max_3hop_exposure_raw = row.max_3hop_exposure_raw,
            a.cumulative_3hop_exposure_raw = row.cumulative_3hop_exposure_raw,
            a.shortest_hop_from_seed = row.shortest_hop_from_seed

        RETURN count(*) AS matched_rows
        """,
        rows=rows,
    ).single()

    return int(record["matched_rows"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()

    if args.batch_size < 500 or args.batch_size > 20000:
        raise ValueError(
            "--batch-size must be between 500 and 20000."
        )

    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    print("=" * 88)
    print(
        "GraphShield AML - Phase 9 - "
        "Neo4j Multi-hop Risk Propagation Loader v1"
    )
    print("=" * 88)

    df = pl.read_parquet(INPUT_PATH)

    missing = [c for c in LOAD_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Propagation artifact is missing columns: {missing}"
        )

    if df["account_key"].n_unique() != df.height:
        raise RuntimeError(
            "Propagation artifact contains duplicate account_key values."
        )

    expected_total = df.height

    if expected_total != 515_088:
        raise RuntimeError(
            f"Unexpected propagation account count: {expected_total:,}"
        )

    valid_hops = {-1, 0, 1, 2, 3}
    observed_hops = set(
        int(x)
        for x in df["shortest_hop_from_seed"].unique().to_list()
    )

    if not observed_hops.issubset(valid_hops):
        raise RuntimeError(
            f"Unexpected shortest-hop values: {sorted(observed_hops)}"
        )

    expected_seed_accounts = df.filter(
        pl.col("shortest_hop_from_seed") == 0
    ).height

    expected_reachable_nonseed = df.filter(
        pl.col("shortest_hop_from_seed") > 0
    ).height

    expected_unreached = df.filter(
        pl.col("shortest_hop_from_seed") < 0
    ).height

    expected_hop1_positive = df.filter(
        pl.col("hop1_exposure_raw") > 0
    ).height

    expected_hop2_positive = df.filter(
        pl.col("hop2_exposure_raw") > 0
    ).height

    expected_hop3_positive = df.filter(
        pl.col("hop3_exposure_raw") > 0
    ).height

    if expected_seed_accounts != 337:
        raise RuntimeError(
            "Unexpected seed-account count in propagation artifact: "
            f"{expected_seed_accounts:,}"
        )

    uri, username, password = resolve_connection()

    print(f"INPUT_ACCOUNTS={expected_total:,}")
    print(f"SEED_ACCOUNTS={expected_seed_accounts:,}")
    print(
        f"REACHABLE_NONSEED_ACCOUNTS="
        f"{expected_reachable_nonseed:,}"
    )
    print(f"UNREACHED_ACCOUNTS={expected_unreached:,}")
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={username}")
    print("NEO4J_PASSWORD=<redacted>")
    print(f"BATCH_SIZE={args.batch_size:,}")

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )

    started = time.perf_counter()
    loaded = 0

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:
            node_state = session.run(
                """
                MATCH (a:Account)
                RETURN
                    count(a) AS total_accounts,
                    count(DISTINCT a.account_id)
                        AS distinct_account_ids
                """
            ).single()

            total_accounts = int(node_state["total_accounts"])
            distinct_account_ids = int(
                node_state["distinct_account_ids"]
            )

            if total_accounts != expected_total:
                raise RuntimeError(
                    "Neo4j Account node count mismatch before load: "
                    f"{total_accounts:,} != {expected_total:,}"
                )

            if distinct_account_ids != expected_total:
                raise RuntimeError(
                    "Neo4j Account.account_id uniqueness verification failed."
                )

            for batch in df.iter_slices(
                n_rows=args.batch_size
            ):
                rows = normalize_rows(batch)

                matched = session.execute_write(
                    write_batch,
                    rows,
                )

                if matched != len(rows):
                    raise RuntimeError(
                        "Propagation batch endpoint mismatch: "
                        f"expected={len(rows):,}, "
                        f"matched={matched:,}"
                    )

                loaded += matched

                print(
                    f"PROPAGATION_LOADED="
                    f"{loaded:,}/{expected_total:,}"
                )

            observed = session.run(
                """
                MATCH (a:Account)
                WHERE a.propagation_version = $version

                RETURN
                    count(a) AS total_accounts,
                    count(DISTINCT a.account_id)
                        AS distinct_accounts,

                    sum(
                        CASE
                            WHEN a.shortest_hop_from_seed = 0
                            THEN 1 ELSE 0
                        END
                    ) AS seed_accounts,

                    sum(
                        CASE
                            WHEN a.shortest_hop_from_seed > 0
                            THEN 1 ELSE 0
                        END
                    ) AS reachable_nonseed_accounts,

                    sum(
                        CASE
                            WHEN a.shortest_hop_from_seed < 0
                            THEN 1 ELSE 0
                        END
                    ) AS unreached_accounts,

                    sum(
                        CASE
                            WHEN a.hop1_exposure_raw > 0
                            THEN 1 ELSE 0
                        END
                    ) AS hop1_positive,

                    sum(
                        CASE
                            WHEN a.hop2_exposure_raw > 0
                            THEN 1 ELSE 0
                        END
                    ) AS hop2_positive,

                    sum(
                        CASE
                            WHEN a.hop3_exposure_raw > 0
                            THEN 1 ELSE 0
                        END
                    ) AS hop3_positive
                """,
                version=VERSION,
            ).single()

            observed_values = {
                "total_accounts": int(
                    observed["total_accounts"]
                ),
                "distinct_accounts": int(
                    observed["distinct_accounts"]
                ),
                "seed_accounts": int(
                    observed["seed_accounts"]
                ),
                "reachable_nonseed_accounts": int(
                    observed["reachable_nonseed_accounts"]
                ),
                "unreached_accounts": int(
                    observed["unreached_accounts"]
                ),
                "hop1_positive": int(
                    observed["hop1_positive"]
                ),
                "hop2_positive": int(
                    observed["hop2_positive"]
                ),
                "hop3_positive": int(
                    observed["hop3_positive"]
                ),
            }

            expected_values = {
                "total_accounts": expected_total,
                "distinct_accounts": expected_total,
                "seed_accounts": expected_seed_accounts,
                "reachable_nonseed_accounts": (
                    expected_reachable_nonseed
                ),
                "unreached_accounts": expected_unreached,
                "hop1_positive": expected_hop1_positive,
                "hop2_positive": expected_hop2_positive,
                "hop3_positive": expected_hop3_positive,
            }

            if observed_values != expected_values:
                raise RuntimeError(
                    "Neo4j propagation verification mismatch. "
                    f"expected={expected_values}, "
                    f"observed={observed_values}"
                )

    finally:
        driver.close()

    elapsed = time.perf_counter() - started

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "4B",
        "version": VERSION,
        "input": str(
            INPUT_PATH.relative_to(PROJECT_ROOT)
        ),
        "expected": expected_values,
        "observed": observed_values,
        "batch_size": args.batch_size,
        "labels_used": False,
        "probability_claim": False,
        "idempotent": True,
        "elapsed_seconds": round(elapsed, 3),
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(f"TOTAL_ACCOUNTS={observed_values['total_accounts']:,}")
    print(f"SEED_ACCOUNTS={observed_values['seed_accounts']:,}")
    print(
        "REACHABLE_NONSEED_ACCOUNTS="
        f"{observed_values['reachable_nonseed_accounts']:,}"
    )
    print(
        f"UNREACHED_ACCOUNTS="
        f"{observed_values['unreached_accounts']:,}"
    )
    print(
        f"HOP1_POSITIVE="
        f"{observed_values['hop1_positive']:,}"
    )
    print(
        f"HOP2_POSITIVE="
        f"{observed_values['hop2_positive']:,}"
    )
    print(
        f"HOP3_POSITIVE="
        f"{observed_values['hop3_positive']:,}"
    )
    print(f"ELAPSED_SECONDS={elapsed:.3f}")
    print(f"REPORT={REPORT_PATH}")
    print("PROBABILITY_CLAIM=FALSE")
    print("LABEL_LEAKAGE=NONE")
    print("NEO4J_RISK_PROPAGATION_VERIFICATION=PASS")
    print("GRAPHSHIELD_PHASE9_STEP4B=PASS")


if __name__ == "__main__":
    main()
