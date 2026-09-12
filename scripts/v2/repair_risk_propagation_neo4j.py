from __future__ import annotations

import argparse
import os
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
ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"
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
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_connection() -> tuple[str, str, str]:
    fenv = parse_dotenv(ENV_PATH)

    def get(*names: str):
        for name in names:
            value = os.environ.get(name) or fenv.get(name)
            if value:
                return value
        return None

    uri = get("NEO4J_URI", "GRAPHSHIELD_NEO4J_URI") or "bolt://127.0.0.1:7687"
    user = get("NEO4J_USER", "NEO4J_USERNAME", "GRAPHSHIELD_NEO4J_USER")
    password = get("NEO4J_PASSWORD", "GRAPHSHIELD_NEO4J_PASSWORD")
    auth = get("NEO4J_AUTH")

    if auth and "/" in auth:
        auth_user, auth_password = auth.split("/", 1)
        user = user or auth_user
        password = password or auth_password

    user = user or "neo4j"

    if not password:
        raise RuntimeError(
            "Neo4j password not found. Load NEO4J_AUTH in this PowerShell session."
        )

    return uri, user, password


def normalize_rows(batch: pl.DataFrame) -> list[dict]:
    rows = []
    for row in batch.select(LOAD_COLUMNS).iter_rows(named=True):
        rows.append(
            {
                **row,
                "hop1_exposure_raw": float(row["hop1_exposure_raw"]),
                "hop2_exposure_raw": float(row["hop2_exposure_raw"]),
                "hop3_exposure_raw": float(row["hop3_exposure_raw"]),
                "hop1_exposure_calibrated": float(row["hop1_exposure_calibrated"]),
                "hop2_exposure_calibrated": float(row["hop2_exposure_calibrated"]),
                "hop3_exposure_calibrated": float(row["hop3_exposure_calibrated"]),
                "max_3hop_exposure_raw": float(row["max_3hop_exposure_raw"]),
                "cumulative_3hop_exposure_raw": float(
                    row["cumulative_3hop_exposure_raw"]
                ),
                "shortest_hop_from_seed": int(row["shortest_hop_from_seed"]),
                "propagation_snapshot_ts": row["propagation_snapshot_ts"].isoformat(),
            }
        )
    return rows


def write_batch(tx, rows: list[dict]) -> int:
    record = tx.run(
        """
        UNWIND $rows AS row
        MATCH (a:Account {account_id: row.account_key})
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
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    df = pl.read_parquet(INPUT_PATH)
    expected_total = df.height

    uri, user, password = resolve_connection()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            missing_rows = session.run(
                """
                MATCH (a:Account)
                WHERE a.propagation_version IS NULL
                   OR a.propagation_version <> $version
                RETURN a.account_id AS account_key
                """,
                version=VERSION,
            ).data()

            missing_ids = [r["account_key"] for r in missing_rows]
            print(f"EXPECTED_TOTAL={expected_total}")
            print(f"MISSING_BEFORE={len(missing_ids)}")

            if missing_ids:
                repair = df.filter(pl.col("account_key").is_in(missing_ids))

                if repair.height != len(missing_ids):
                    raise RuntimeError(
                        f"Missing-ID mismatch: Neo4j={len(missing_ids)}, parquet={repair.height}"
                    )

                loaded = 0
                for batch in repair.iter_slices(n_rows=args.batch_size):
                    rows = normalize_rows(batch)
                    matched = session.execute_write(write_batch, rows)

                    if matched != len(rows):
                        raise RuntimeError(
                            f"Repair batch mismatch: expected={len(rows)}, matched={matched}"
                        )

                    loaded += matched
                    print(f"REPAIRED={loaded}/{repair.height}")

            record = session.run(
                """
                MATCH (a:Account)
                WHERE a.propagation_version = $version
                RETURN count(a) AS loaded
                """,
                version=VERSION,
            ).single()

            loaded_total = int(record["loaded"])

    finally:
        driver.close()

    print(f"NEO4J_LOADED={loaded_total}")

    if loaded_total != expected_total:
        raise RuntimeError(
            f"Repair incomplete: Neo4j={loaded_total}, expected={expected_total}"
        )

    print("NEO4J_RISK_PROPAGATION_REPAIR=PASS")
    print("GRAPHSHIELD_PHASE9_STEP4B=PASS")


if __name__ == "__main__":
    main()
