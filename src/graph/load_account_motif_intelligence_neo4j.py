from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    / "account_motif_intelligence_v1.parquet"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase9"
    / "neo4j_account_motif_intelligence_v1_report.json"
)

ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"

VERSION = "account_motif_intelligence_v1"

LOAD_COLUMNS = [
    "account_key",
    "sender_snapshot_tx_count",
    "receiver_snapshot_tx_count",
    "rapid_pass_through_tx_count",
    "two_node_cycle_close_tx_count",
    "max_sender_fanout_ratio_1h",
    "max_sender_fanout_ratio_24h",
    "max_receiver_fanin_ratio_1h",
    "max_receiver_fanin_ratio_24h",
    "has_rapid_pass_through_signal",
    "has_two_node_cycle_signal",
    "has_any_motif_signal",
    "motif_snapshot_ts",
    "motif_version",
]


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}

    if not path.exists():
        return out

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")

    return out


def docker_neo4j_auth() -> str | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "graphshield-neo4j",
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("NEO4J_AUTH="):
            return line.split("=", 1)[1].strip()

    return None


def resolve_connection() -> tuple[str, str, str]:
    fenv = parse_dotenv(ENV_PATH)

    def get(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name) or fenv.get(name)
            if value:
                return value
        return None

    uri = (
        get("NEO4J_URI", "GRAPHSHIELD_NEO4J_URI")
        or "bolt://127.0.0.1:7687"
    )

    user = get(
        "NEO4J_USER",
        "NEO4J_USERNAME",
        "GRAPHSHIELD_NEO4J_USER",
    )

    password = get(
        "NEO4J_PASSWORD",
        "GRAPHSHIELD_NEO4J_PASSWORD",
    )

    auth = get("NEO4J_AUTH") or docker_neo4j_auth()

    if auth and "/" in auth:
        auth_user, auth_password = auth.split("/", 1)
        user = user or auth_user
        password = password or auth_password

    user = user or "neo4j"

    if not password:
        raise RuntimeError(
            "Neo4j credentials were not found in the shell, infra/v2/.env, "
            "or the running graphshield-neo4j container."
        )

    return uri, user, password


def normalize_rows(batch: pl.DataFrame) -> list[dict]:
    rows: list[dict] = []

    for row in batch.select(LOAD_COLUMNS).iter_rows(named=True):
        rows.append(
            {
                "account_key": row["account_key"],
                "sender_snapshot_tx_count": int(row["sender_snapshot_tx_count"]),
                "receiver_snapshot_tx_count": int(row["receiver_snapshot_tx_count"]),
                "rapid_pass_through_tx_count": int(
                    row["rapid_pass_through_tx_count"]
                ),
                "two_node_cycle_close_tx_count": int(
                    row["two_node_cycle_close_tx_count"]
                ),
                "max_sender_fanout_ratio_1h": float(
                    row["max_sender_fanout_ratio_1h"]
                ),
                "max_sender_fanout_ratio_24h": float(
                    row["max_sender_fanout_ratio_24h"]
                ),
                "max_receiver_fanin_ratio_1h": float(
                    row["max_receiver_fanin_ratio_1h"]
                ),
                "max_receiver_fanin_ratio_24h": float(
                    row["max_receiver_fanin_ratio_24h"]
                ),
                "has_rapid_pass_through_signal": bool(
                    row["has_rapid_pass_through_signal"]
                ),
                "has_two_node_cycle_signal": bool(
                    row["has_two_node_cycle_signal"]
                ),
                "has_any_motif_signal": bool(
                    row["has_any_motif_signal"]
                ),
                "motif_snapshot_ts": row["motif_snapshot_ts"].isoformat(),
                "motif_version": row["motif_version"],
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
            a.motif_version = row.motif_version,
            a.motif_snapshot_ts = datetime(row.motif_snapshot_ts),
            a.sender_snapshot_tx_count = row.sender_snapshot_tx_count,
            a.receiver_snapshot_tx_count = row.receiver_snapshot_tx_count,
            a.rapid_pass_through_tx_count = row.rapid_pass_through_tx_count,
            a.two_node_cycle_close_tx_count = row.two_node_cycle_close_tx_count,
            a.max_sender_fanout_ratio_1h = row.max_sender_fanout_ratio_1h,
            a.max_sender_fanout_ratio_24h = row.max_sender_fanout_ratio_24h,
            a.max_receiver_fanin_ratio_1h = row.max_receiver_fanin_ratio_1h,
            a.max_receiver_fanin_ratio_24h = row.max_receiver_fanin_ratio_24h,
            a.has_rapid_pass_through_signal = row.has_rapid_pass_through_signal,
            a.has_two_node_cycle_signal = row.has_two_node_cycle_signal,
            a.has_any_motif_signal = row.has_any_motif_signal

        RETURN count(*) AS matched_rows
        """,
        rows=rows,
    ).single()

    return int(record["matched_rows"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    if args.batch_size < 250 or args.batch_size > 5000:
        raise ValueError("--batch-size must be between 250 and 5000.")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    print("=" * 88)
    print(
        "GraphShield AML - Phase 9 - "
        "Neo4j Account Motif Intelligence Loader v1"
    )
    print("=" * 88)

    df = pl.read_parquet(INPUT_PATH)

    missing = [c for c in LOAD_COLUMNS if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"Motif artifact is missing required columns: {missing}"
        )

    if df["account_key"].n_unique() != df.height:
        raise RuntimeError(
            "Motif artifact contains duplicate account_key values."
        )

    expected_total = df.height

    if expected_total != 515_088:
        raise RuntimeError(
            f"Unexpected account count: {expected_total:,}"
        )

    expected_rapid = df.filter(
        pl.col("has_rapid_pass_through_signal")
    ).height

    expected_cycle = df.filter(
        pl.col("has_two_node_cycle_signal")
    ).height

    expected_any = df.filter(
        pl.col("has_any_motif_signal")
    ).height

    uri, user, password = resolve_connection()

    print(f"INPUT_ACCOUNTS={expected_total:,}")
    print(f"RAPID_SIGNAL_ACCOUNTS={expected_rapid:,}")
    print(f"CYCLE_SIGNAL_ACCOUNTS={expected_cycle:,}")
    print(f"ANY_MOTIF_ACCOUNTS={expected_any:,}")
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={user}")
    print("NEO4J_PASSWORD=<redacted>")
    print(f"BATCH_SIZE={args.batch_size:,}")

    driver = GraphDatabase.driver(
        uri,
        auth=(user, password),
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

            total_accounts = int(
                node_state["total_accounts"]
            )

            distinct_accounts = int(
                node_state["distinct_account_ids"]
            )

            if total_accounts != expected_total:
                raise RuntimeError(
                    "Neo4j Account node count mismatch: "
                    f"{total_accounts:,} != {expected_total:,}"
                )

            if distinct_accounts != expected_total:
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
                        "Motif batch endpoint mismatch: "
                        f"expected={len(rows):,}, "
                        f"matched={matched:,}"
                    )

                loaded += matched

                if loaded % 10000 == 0 or loaded == expected_total:
                    print(
                        f"MOTIF_LOADED="
                        f"{loaded:,}/{expected_total:,}"
                    )

            observed = session.run(
                """
                MATCH (a:Account)
                WHERE a.motif_version = $version

                RETURN
                    count(a) AS total_accounts,

                    sum(
                        CASE
                            WHEN a.has_rapid_pass_through_signal
                            THEN 1 ELSE 0
                        END
                    ) AS rapid_accounts,

                    sum(
                        CASE
                            WHEN a.has_two_node_cycle_signal
                            THEN 1 ELSE 0
                        END
                    ) AS cycle_accounts,

                    sum(
                        CASE
                            WHEN a.has_any_motif_signal
                            THEN 1 ELSE 0
                        END
                    ) AS any_motif_accounts
                """,
                version=VERSION,
            ).single()

            observed_total = int(
                observed["total_accounts"]
            )
            observed_rapid = int(
                observed["rapid_accounts"]
            )
            observed_cycle = int(
                observed["cycle_accounts"]
            )
            observed_any = int(
                observed["any_motif_accounts"]
            )

            expected_values = {
                "total_accounts": expected_total,
                "rapid_accounts": expected_rapid,
                "cycle_accounts": expected_cycle,
                "any_motif_accounts": expected_any,
            }

            observed_values = {
                "total_accounts": observed_total,
                "rapid_accounts": observed_rapid,
                "cycle_accounts": observed_cycle,
                "any_motif_accounts": observed_any,
            }

            if observed_values != expected_values:
                raise RuntimeError(
                    "Neo4j motif verification mismatch. "
                    f"expected={expected_values}, "
                    f"observed={observed_values}"
                )

    finally:
        driver.close()

    elapsed = time.perf_counter() - started

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "5B",
        "version": VERSION,
        "input": str(
            INPUT_PATH.relative_to(PROJECT_ROOT)
        ),
        "expected": expected_values,
        "observed": observed_values,
        "batch_size": args.batch_size,
        "labels_used": False,
        "composite_probability_created": False,
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

    print(f"TOTAL_ACCOUNTS={observed_total:,}")
    print(f"RAPID_SIGNAL_ACCOUNTS={observed_rapid:,}")
    print(f"CYCLE_SIGNAL_ACCOUNTS={observed_cycle:,}")
    print(f"ANY_MOTIF_ACCOUNTS={observed_any:,}")
    print(f"ELAPSED_SECONDS={elapsed:.3f}")
    print(f"REPORT={REPORT_PATH}")
    print("COMPOSITE_PROBABILITY_CREATED=FALSE")
    print("LABEL_LEAKAGE=NONE")
    print("NEO4J_MOTIF_VERIFICATION=PASS")
    print("GRAPHSHIELD_PHASE9_STEP5B=PASS")


if __name__ == "__main__":
    main()
