from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import polars as pl
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "graph" / "account_risk_v1.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "v2" / "phase9" / "neo4j_account_risk_load_v1_report.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"

RISK_VERSION = "account_risk_v1"
RISK_SOURCE = "champion_test_predictions.parquet"

SCORED_PROPERTIES = [
    "mean_risk_raw",
    "p95_risk_raw",
    "max_risk_raw",
    "mean_risk_calibrated",
    "p95_risk_calibrated",
    "max_risk_calibrated",
    "risk_exposure_sum_calibrated",
    "high_risk_txn_rate",
    "outbound_scored_txn_count",
    "outbound_risk_mean_raw",
    "outbound_risk_mean_calibrated",
    "outbound_risk_max_raw",
    "inbound_scored_txn_count",
    "inbound_risk_mean_raw",
    "inbound_risk_mean_calibrated",
    "inbound_risk_max_raw",
    "entity_risk_seed_raw",
    "entity_risk_seed_calibrated",
    "high_risk_threshold_raw",
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
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def resolve_connection() -> tuple[str, str, str]:
    file_env = parse_dotenv(DEFAULT_ENV_PATH)

    def get(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
            value = file_env.get(name)
            if value:
                return value
        return None

    uri = get("NEO4J_URI", "GRAPHSHIELD_NEO4J_URI") or "bolt://127.0.0.1:7687"
    username = get("NEO4J_USER", "NEO4J_USERNAME", "GRAPHSHIELD_NEO4J_USER")
    password = get("NEO4J_PASSWORD", "GRAPHSHIELD_NEO4J_PASSWORD")
    auth = get("NEO4J_AUTH")

    if auth and "/" in auth:
        auth_user, auth_password = auth.split("/", 1)
        username = username or auth_user
        password = password or auth_password

    username = username or "neo4j"

    if not password:
        raise RuntimeError(
            "Neo4j password was not found in the process environment or "
            "infra/v2/.env. Expected NEO4J_PASSWORD, GRAPHSHIELD_NEO4J_PASSWORD, "
            "or NEO4J_AUTH=user/password. The script will not print secrets."
        )

    return uri, username, password


def write_all_nodes(tx, rows: list[dict]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (a:Account {account_id: row.account_key})
        SET a.bank_id = row.bank_id,
            a.risk_version = $risk_version,
            a.risk_source = $risk_source,
            a.risk_scope = row.risk_scope,
            a.scored_txn_count = row.scored_txn_count,
            a.high_risk_txn_count = row.high_risk_txn_count,
            a.entity_risk_seed_raw = row.entity_risk_seed_raw,
            a.entity_risk_seed_calibrated = row.entity_risk_seed_calibrated
        """,
        rows=rows,
        risk_version=RISK_VERSION,
        risk_source=RISK_SOURCE,
    ).consume()


def write_scored_nodes(tx, rows: list[dict]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (a:Account {account_id: row.account_key})
        SET a.mean_risk_raw = row.mean_risk_raw,
            a.p95_risk_raw = row.p95_risk_raw,
            a.max_risk_raw = row.max_risk_raw,
            a.mean_risk_calibrated = row.mean_risk_calibrated,
            a.p95_risk_calibrated = row.p95_risk_calibrated,
            a.max_risk_calibrated = row.max_risk_calibrated,
            a.risk_exposure_sum_calibrated = row.risk_exposure_sum_calibrated,
            a.high_risk_txn_rate = row.high_risk_txn_rate,
            a.outbound_scored_txn_count = row.outbound_scored_txn_count,
            a.outbound_risk_mean_raw = row.outbound_risk_mean_raw,
            a.outbound_risk_mean_calibrated = row.outbound_risk_mean_calibrated,
            a.outbound_risk_max_raw = row.outbound_risk_max_raw,
            a.inbound_scored_txn_count = row.inbound_scored_txn_count,
            a.inbound_risk_mean_raw = row.inbound_risk_mean_raw,
            a.inbound_risk_mean_calibrated = row.inbound_risk_mean_calibrated,
            a.inbound_risk_max_raw = row.inbound_risk_max_raw,
            a.high_risk_threshold_raw = row.high_risk_threshold_raw
        """,
        rows=rows,
    ).consume()


def verify(session, expected_total: int, expected_scored: int, expected_high: int) -> dict:
    result = session.run(
        """
        MATCH (a:Account)
        WHERE a.risk_version = $risk_version
        RETURN
            count(a) AS total_accounts,
            sum(CASE WHEN a.scored_txn_count > 0 THEN 1 ELSE 0 END) AS scored_accounts,
            sum(CASE WHEN a.high_risk_txn_count > 0 THEN 1 ELSE 0 END) AS high_risk_accounts,
            count(DISTINCT a.account_id) AS distinct_account_ids
        """,
        risk_version=RISK_VERSION,
    ).single()

    observed = {
        "total_accounts": int(result["total_accounts"]),
        "scored_accounts": int(result["scored_accounts"]),
        "high_risk_accounts": int(result["high_risk_accounts"]),
        "distinct_account_ids": int(result["distinct_account_ids"]),
    }

    expected = {
        "total_accounts": expected_total,
        "scored_accounts": expected_scored,
        "high_risk_accounts": expected_high,
        "distinct_account_ids": expected_total,
    }

    if observed != expected:
        raise RuntimeError(
            "Neo4j verification mismatch. "
            f"expected={expected}, observed={observed}"
        )

    return observed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()

    if args.batch_size < 100 or args.batch_size > 20000:
        raise ValueError("--batch-size must be between 100 and 20000.")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    print("=" * 88)
    print("GraphShield AML - Phase 9 - Neo4j Account Risk Loader v1")
    print("=" * 88)

    df = pl.read_parquet(INPUT_PATH)

    if df["account_key"].n_unique() != df.height:
        raise RuntimeError("account_risk_v1 contains duplicate account_key values.")

    expected_total = df.height
    expected_scored = df.filter(pl.col("scored_txn_count") > 0).height
    expected_high = df.filter(pl.col("high_risk_txn_count") > 0).height

    uri, username, password = resolve_connection()

    print(f"INPUT_ACCOUNTS={expected_total:,}")
    print(f"EXPECTED_SCORED_ACCOUNTS={expected_scored:,}")
    print(f"EXPECTED_HIGH_RISK_ACCOUNTS={expected_high:,}")
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={username}")
    print("NEO4J_PASSWORD=<redacted>")
    print(f"BATCH_SIZE={args.batch_size:,}")

    started = time.perf_counter()

    driver = GraphDatabase.driver(uri, auth=(username, password))

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:
            session.run(
                """
                CREATE CONSTRAINT account_id_unique IF NOT EXISTS
                FOR (a:Account)
                REQUIRE a.account_id IS UNIQUE
                """
            ).consume()

            loaded = 0
            scored_loaded = 0

            for batch in df.iter_slices(n_rows=args.batch_size):
                base_cols = [
                    "account_key",
                    "bank_id",
                    "risk_scope",
                    "scored_txn_count",
                    "high_risk_txn_count",
                    "entity_risk_seed_raw",
                    "entity_risk_seed_calibrated",
                ]

                all_rows = batch.select(base_cols).to_dicts()
                scored_batch = batch.filter(pl.col("scored_txn_count") > 0)

                session.execute_write(write_all_nodes, all_rows)

                if scored_batch.height:
                    scored_cols = ["account_key"] + SCORED_PROPERTIES
                    scored_rows = scored_batch.select(scored_cols).to_dicts()
                    session.execute_write(write_scored_nodes, scored_rows)
                    scored_loaded += scored_batch.height

                loaded += batch.height
                print(
                    f"LOADED={loaded:,}/{expected_total:,} "
                    f"SCORED_UPDATED={scored_loaded:,}/{expected_scored:,}"
                )

            observed = verify(
                session,
                expected_total=expected_total,
                expected_scored=expected_scored,
                expected_high=expected_high,
            )

    finally:
        driver.close()

    elapsed = time.perf_counter() - started

    report = {
        "status": "PASS",
        "artifact": RISK_VERSION,
        "source": str(INPUT_PATH.relative_to(PROJECT_ROOT)),
        "neo4j_uri": uri,
        "neo4j_user": username,
        "password_logged": False,
        "batch_size": args.batch_size,
        "expected": {
            "total_accounts": expected_total,
            "scored_accounts": expected_scored,
            "high_risk_accounts": expected_high,
        },
        "observed": observed,
        "elapsed_seconds": round(elapsed, 3),
        "idempotent": True,
        "label_properties_loaded": False,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"TOTAL_ACCOUNTS={observed['total_accounts']:,}")
    print(f"SCORED_ACCOUNTS={observed['scored_accounts']:,}")
    print(f"HIGH_RISK_ACCOUNTS={observed['high_risk_accounts']:,}")
    print(f"DISTINCT_ACCOUNT_IDS={observed['distinct_account_ids']:,}")
    print(f"ELAPSED_SECONDS={elapsed:.3f}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_PROPERTIES_LOADED=FALSE")
    print("NEO4J_ACCOUNT_RISK_VERIFICATION=PASS")
    print("GRAPHSHIELD_PHASE9_STEP1B=PASS")


if __name__ == "__main__":
    main()
