from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import polars as pl
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]

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
    / "neo4j_suspicious_communities_v1_report.json"
)

DEFAULT_ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"

COMMUNITY_VERSION = "suspicious_communities_v1"


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


def write_community_nodes(tx, rows: list[dict]) -> None:
    tx.run(
        """
        UNWIND $rows AS row

        MERGE (c:SuspiciousCommunity {
            community_id: row.community_id
        })

        SET
            c.version = $version,
            c.community_priority_rank = row.community_priority_rank,
            c.member_count = row.member_count,
            c.high_risk_seed_count = row.high_risk_seed_count,
            c.scored_account_count = row.scored_account_count,
            c.max_entity_risk_seed_raw = row.max_entity_risk_seed_raw,
            c.max_entity_risk_seed_calibrated = row.max_entity_risk_seed_calibrated,
            c.mean_entity_risk_seed_raw = row.mean_entity_risk_seed_raw,
            c.risk_exposure_sum_calibrated = row.risk_exposure_sum_calibrated,
            c.internal_transaction_count = row.internal_transaction_count,
            c.internal_amount_paid = row.internal_amount_paid
        """,
        rows=rows,
        version=COMMUNITY_VERSION,
    ).consume()


def write_membership_batch(tx, rows: list[dict]) -> int:
    record = tx.run(
        """
        UNWIND $rows AS row

        MATCH (a:Account {
            account_id: row.account_key
        })

        MATCH (c:SuspiciousCommunity {
            community_id: row.community_id
        })

        SET
            a.community_id = row.community_id,
            a.community_version = $version,
            a.community_priority_rank = row.community_priority_rank,
            a.community_member_count = row.member_count,
            a.community_high_risk_seed_count = row.high_risk_seed_count,
            a.community_max_entity_risk_seed_raw = row.max_entity_risk_seed_raw,
            a.community_internal_transaction_count = row.internal_transaction_count,
            a.community_is_high_risk_seed = row.is_high_risk_seed

        MERGE (a)-[r:MEMBER_OF_COMMUNITY {
            version: $version
        }]->(c)

        RETURN count(*) AS matched_rows
        """,
        rows=rows,
        version=COMMUNITY_VERSION,
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

    for path in (MEMBERSHIP_PATH, SUMMARY_PATH):
        if not path.exists():
            raise FileNotFoundError(path)

    print("=" * 88)
    print(
        "GraphShield AML - Phase 9 - "
        "Neo4j Suspicious Community Loader v1"
    )
    print("=" * 88)

    membership = pl.read_parquet(MEMBERSHIP_PATH)
    summary = pl.read_parquet(SUMMARY_PATH)

    if membership["account_key"].n_unique() != membership.height:
        raise RuntimeError(
            "Community membership contains duplicate account_key values."
        )

    if summary["community_id"].n_unique() != summary.height:
        raise RuntimeError(
            "Community summary contains duplicate community_id values."
        )

    expected_memberships = membership.height
    expected_communities = summary.height

    expected_high_risk_communities = (
        summary.filter(
            pl.col("high_risk_seed_count") > 0
        ).height
    )

    membership_enriched = membership.join(
        summary.select(
            [
                "community_id",
                "community_priority_rank",
                "member_count",
                "high_risk_seed_count",
                "max_entity_risk_seed_raw",
                "internal_transaction_count",
            ]
        ),
        on="community_id",
        how="left",
    )

    if membership_enriched["community_priority_rank"].null_count() > 0:
        raise RuntimeError(
            "Membership-to-summary join produced missing community context."
        )

    community_rows = summary.select(
        [
            "community_id",
            "community_priority_rank",
            "member_count",
            "high_risk_seed_count",
            "scored_account_count",
            "max_entity_risk_seed_raw",
            "max_entity_risk_seed_calibrated",
            "mean_entity_risk_seed_raw",
            "risk_exposure_sum_calibrated",
            "internal_transaction_count",
            "internal_amount_paid",
        ]
    ).to_dicts()

    uri, username, password = resolve_connection()

    print(f"COMMUNITIES={expected_communities:,}")
    print(f"MEMBERSHIPS={expected_memberships:,}")
    print(
        "HIGH_RISK_COMMUNITIES="
        f"{expected_high_risk_communities:,}"
    )
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={username}")
    print("NEO4J_PASSWORD=<redacted>")
    print(f"BATCH_SIZE={args.batch_size:,}")

    started = time.perf_counter()

    driver = GraphDatabase.driver(
        uri,
        auth=(username, password),
    )

    loaded_memberships = 0

    try:
        driver.verify_connectivity()

        with driver.session(database="neo4j") as session:
            session.run(
                """
                CREATE CONSTRAINT suspicious_community_id_unique
                IF NOT EXISTS
                FOR (c:SuspiciousCommunity)
                REQUIRE c.community_id IS UNIQUE
                """
            ).consume()

            # Community summary is small enough for one transaction.
            session.execute_write(
                write_community_nodes,
                community_rows,
            )

            for batch in membership_enriched.iter_slices(
                n_rows=args.batch_size
            ):
                rows = batch.select(
                    [
                        "account_key",
                        "community_id",
                        "community_priority_rank",
                        "member_count",
                        "high_risk_seed_count",
                        "max_entity_risk_seed_raw",
                        "internal_transaction_count",
                        "is_high_risk_seed",
                    ]
                ).to_dicts()

                matched = session.execute_write(
                    write_membership_batch,
                    rows,
                )

                if matched != len(rows):
                    raise RuntimeError(
                        "Membership batch mismatch: "
                        f"expected={len(rows):,}, "
                        f"matched={matched:,}"
                    )

                loaded_memberships += matched

                print(
                    f"MEMBERSHIP_LOADED="
                    f"{loaded_memberships:,}/"
                    f"{expected_memberships:,}"
                )

            observed = session.run(
                """
                MATCH (c:SuspiciousCommunity)
                WHERE c.version = $version

                WITH count(c) AS communities

                MATCH (a:Account)-[
                    r:MEMBER_OF_COMMUNITY {
                        version: $version
                    }
                ]->(c:SuspiciousCommunity)

                RETURN
                    communities,
                    count(r) AS memberships,
                    count(DISTINCT a.account_id)
                        AS distinct_accounts,
                    count(DISTINCT c.community_id)
                        AS communities_with_members
                """,
                version=COMMUNITY_VERSION,
            ).single()

            observed_communities = int(
                observed["communities"]
            )

            observed_memberships = int(
                observed["memberships"]
            )

            observed_distinct_accounts = int(
                observed["distinct_accounts"]
            )

            observed_communities_with_members = int(
                observed["communities_with_members"]
            )

            if observed_communities != expected_communities:
                raise RuntimeError(
                    "Community node count mismatch: "
                    f"{observed_communities:,} != "
                    f"{expected_communities:,}"
                )

            if observed_memberships != expected_memberships:
                raise RuntimeError(
                    "Membership relationship count mismatch: "
                    f"{observed_memberships:,} != "
                    f"{expected_memberships:,}"
                )

            if (
                observed_distinct_accounts
                != expected_memberships
            ):
                raise RuntimeError(
                    "Distinct account membership mismatch."
                )

            if (
                observed_communities_with_members
                != expected_communities
            ):
                raise RuntimeError(
                    "One or more community nodes have no members."
                )

    finally:
        driver.close()

    elapsed = time.perf_counter() - started

    report = {
        "status": "PASS",
        "phase": 9,
        "step": "3B",
        "version": COMMUNITY_VERSION,
        "community_nodes": observed_communities,
        "membership_relationships": (
            observed_memberships
        ),
        "distinct_member_accounts": (
            observed_distinct_accounts
        ),
        "communities_with_members": (
            observed_communities_with_members
        ),
        "high_risk_communities": (
            expected_high_risk_communities
        ),
        "labels_used": False,
        "idempotent": True,
        "elapsed_seconds": round(elapsed, 3),
        "membership_source": str(
            MEMBERSHIP_PATH.relative_to(PROJECT_ROOT)
        ),
        "summary_source": str(
            SUMMARY_PATH.relative_to(PROJECT_ROOT)
        ),
    }

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print(
        f"COMMUNITY_NODES={observed_communities:,}"
    )
    print(
        "MEMBERSHIP_RELATIONSHIPS="
        f"{observed_memberships:,}"
    )
    print(
        "DISTINCT_MEMBER_ACCOUNTS="
        f"{observed_distinct_accounts:,}"
    )
    print(f"ELAPSED_SECONDS={elapsed:.3f}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_LEAKAGE=NONE")
    print(
        "NEO4J_COMMUNITY_VERIFICATION=PASS"
    )
    print("GRAPHSHIELD_PHASE9_STEP3B=PASS")


if __name__ == "__main__":
    main()
