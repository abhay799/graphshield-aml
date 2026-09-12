from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pyarrow.parquet as pq
from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "data" / "processed" / "graph" / "transaction_edges.parquet"
REPORT_PATH = PROJECT_ROOT / "reports" / "v2" / "phase9" / "neo4j_transaction_load_v1_report.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"

LOADER_VERSION = "phase9_transfer_v1"
COLUMNS = [
    "transaction_id",
    "event_ts",
    "from_account_key",
    "to_account_key",
    "amount_paid",
    "amount_received",
    "payment_currency",
    "receiving_currency",
    "payment_format",
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
            "Neo4j password was not found in the process environment or infra/v2/.env. "
            "Expected NEO4J_PASSWORD, GRAPHSHIELD_NEO4J_PASSWORD, or NEO4J_AUTH=user/password."
        )

    return uri, username, password


def normalize_rows(batch) -> list[dict]:
    data = batch.to_pydict()
    rows: list[dict] = []

    for i in range(batch.num_rows):
        ts = data["event_ts"][i]
        if ts is None:
            raise RuntimeError(f"Null event_ts encountered at batch row {i}.")

        rows.append(
            {
                "transaction_id": data["transaction_id"][i],
                "event_ts": ts.isoformat(),
                "from_account_key": data["from_account_key"][i],
                "to_account_key": data["to_account_key"][i],
                "amount_paid": float(data["amount_paid"][i]),
                "amount_received": float(data["amount_received"][i]),
                "payment_currency": data["payment_currency"][i],
                "receiving_currency": data["receiving_currency"][i],
                "payment_format": data["payment_format"][i],
            }
        )

    return rows


def load_batch(tx, rows: list[dict]) -> int:
    record = tx.run(
        '''
        UNWIND $rows AS row
        MATCH (src:Account {account_id: row.from_account_key})
        MATCH (dst:Account {account_id: row.to_account_key})
        MERGE (src)-[r:TRANSFER {transaction_id: row.transaction_id}]->(dst)
        SET
            r.event_ts = datetime(row.event_ts),
            r.amount_paid = row.amount_paid,
            r.amount_received = row.amount_received,
            r.payment_currency = row.payment_currency,
            r.receiving_currency = row.receiving_currency,
            r.payment_format = row.payment_format,
            r.loader_version = $loader_version
        RETURN count(*) AS matched_rows
        ''',
        rows=rows,
        loader_version=LOADER_VERSION,
    ).single()

    return int(record["matched_rows"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args()

    if args.batch_size < 500 or args.batch_size > 10000:
        raise ValueError("--batch-size must be between 500 and 10000.")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    print("=" * 88)
    print("GraphShield AML - Phase 9 - Neo4j Transaction Relationship Loader v1")
    print("=" * 88)

    parquet = pq.ParquetFile(INPUT_PATH)
    expected_rows = int(parquet.metadata.num_rows)

    if expected_rows <= 0:
        raise RuntimeError("transaction_edges.parquet is empty.")

    schema_names = set(parquet.schema_arrow.names)
    missing = [c for c in COLUMNS if c not in schema_names]
    if missing:
        raise RuntimeError(f"Required columns missing: {missing}")

    if "is_laundering" in COLUMNS:
        raise RuntimeError(
            "Ground-truth label must never be loaded as a production graph relationship property."
        )

    uri, username, password = resolve_connection()

    print(f"INPUT={INPUT_PATH}")
    print(f"EXPECTED_TRANSACTIONS={expected_rows:,}")
    print(f"BATCH_SIZE={args.batch_size:,}")
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={username}")
    print("NEO4J_PASSWORD=<redacted>")
    print("LABEL_PROPERTY_LOADED=FALSE")

    started = time.perf_counter()
    driver = GraphDatabase.driver(uri, auth=(username, password))

    loaded_rows = 0
    batch_number = 0

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:
            account_state = session.run(
                '''
                MATCH (a:Account)
                RETURN count(a) AS total_accounts,
                       count(DISTINCT a.account_id) AS distinct_account_ids
                '''
            ).single()

            total_accounts = int(account_state["total_accounts"])
            distinct_account_ids = int(account_state["distinct_account_ids"])

            if total_accounts != 515_088:
                raise RuntimeError(
                    f"Unexpected Account node count before relationship load: {total_accounts:,}"
                )

            if distinct_account_ids != total_accounts:
                raise RuntimeError("Duplicate Account.account_id values detected.")

            session.run(
                '''
                CREATE INDEX transfer_transaction_id IF NOT EXISTS
                FOR ()-[r:TRANSFER]-()
                ON (r.transaction_id)
                '''
            ).consume()

            existing = session.run(
                "MATCH ()-[r:TRANSFER]->() RETURN count(r) AS n"
            ).single()

            existing_transfer_count = int(existing["n"])
            print(f"EXISTING_TRANSFER_RELATIONSHIPS={existing_transfer_count:,}")

            for batch in parquet.iter_batches(
                batch_size=args.batch_size,
                columns=COLUMNS,
            ):
                batch_number += 1
                rows = normalize_rows(batch)

                matched = session.execute_write(load_batch, rows)

                if matched != len(rows):
                    raise RuntimeError(
                        "Batch endpoint match mismatch: "
                        f"expected={len(rows):,}, matched={matched:,}, batch={batch_number:,}"
                    )

                loaded_rows += matched

                if (
                    batch_number % args.progress_every == 0
                    or loaded_rows == expected_rows
                ):
                    elapsed = time.perf_counter() - started
                    rate = loaded_rows / elapsed if elapsed > 0 else 0.0

                    print(
                        f"PROCESSED={loaded_rows:,}/{expected_rows:,} "
                        f"BATCH={batch_number:,} RATE={rate:,.0f}_rows_per_sec"
                    )

            if loaded_rows != expected_rows:
                raise RuntimeError(
                    f"Loader processed {loaded_rows:,} rows, expected {expected_rows:,}."
                )

            observed = session.run(
                '''
                MATCH ()-[r:TRANSFER]->()
                WHERE r.loader_version = $loader_version
                RETURN count(r) AS transfer_count,
                       count(DISTINCT r.transaction_id) AS distinct_transaction_ids
                ''',
                loader_version=LOADER_VERSION,
            ).single()

            transfer_count = int(observed["transfer_count"])
            distinct_transaction_ids = int(observed["distinct_transaction_ids"])

            if transfer_count != expected_rows:
                raise RuntimeError(
                    f"Final TRANSFER count mismatch: {transfer_count:,} != {expected_rows:,}"
                )

            if distinct_transaction_ids != expected_rows:
                raise RuntimeError(
                    "Duplicate or missing transaction IDs in Neo4j: "
                    f"{distinct_transaction_ids:,} distinct for {expected_rows:,} expected."
                )

    finally:
        driver.close()

    elapsed = time.perf_counter() - started

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "2B",
        "artifact": "neo4j_transfer_relationships_v1",
        "source": str(INPUT_PATH.relative_to(PROJECT_ROOT)),
        "expected_transactions": expected_rows,
        "processed_rows": loaded_rows,
        "transfer_relationships": transfer_count,
        "distinct_transaction_ids": distinct_transaction_ids,
        "existing_transfer_relationships_before_run": existing_transfer_count,
        "account_nodes": total_accounts,
        "batch_size": args.batch_size,
        "loader_version": LOADER_VERSION,
        "idempotent_merge": True,
        "label_property_loaded": False,
        "elapsed_seconds": round(elapsed, 3),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"TRANSFER_RELATIONSHIPS={transfer_count:,}")
    print(f"DISTINCT_TRANSACTION_IDS={distinct_transaction_ids:,}")
    print(f"ELAPSED_SECONDS={elapsed:.3f}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_PROPERTY_LOADED=FALSE")
    print("NEO4J_TRANSACTION_RELATIONSHIP_VERIFICATION=PASS")
    print("GRAPHSHIELD_PHASE9_STEP2B=PASS")


if __name__ == "__main__":
    main()
