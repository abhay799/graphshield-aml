from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from confluent_kafka import Consumer, KafkaError, TopicPartition
from neo4j import GraphDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "v2" / "streaming" / "replay.yaml"
DEFAULT_ENV = PROJECT_ROOT / "infra" / "v2" / ".env"
REPORT_PATH = PROJECT_ROOT / "reports" / "v2" / "phase9" / "online_graph_consumer_v1_report.json"

ONLINE_VERSION = "online_graph_v1"
DEFAULT_GROUP_ID = "graphshield-online-graph-v1"
STOP_REQUESTED = False


def handle_signal(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


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


def resolve_neo4j() -> tuple[str, str, str]:
    file_env = parse_dotenv(DEFAULT_ENV)

    def get(*names: str) -> str | None:
        for name in names:
            value = os.environ.get(name) or file_env.get(name)
            if value:
                return value
        return None

    uri = get("NEO4J_URI", "GRAPHSHIELD_NEO4J_URI") or "bolt://127.0.0.1:7687"
    user = get("NEO4J_USER", "NEO4J_USERNAME", "GRAPHSHIELD_NEO4J_USER")
    password = get("NEO4J_PASSWORD", "GRAPHSHIELD_NEO4J_PASSWORD")
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


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    if not isinstance(config, dict):
        raise RuntimeError("Streaming config is not a mapping.")
    return config


def account_key(bank, account) -> str:
    return f"{bank}::{account}"


def normalize_event(payload: bytes) -> dict:
    event = json.loads(payload.decode("utf-8"))

    required = [
        "transaction_id",
        "event_ts",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_paid",
        "amount_received",
        "payment_currency",
        "receiving_currency",
        "payment_format",
        "source_row_number",
    ]

    missing = [name for name in required if name not in event]
    if missing:
        raise RuntimeError(f"Kafka event missing required fields: {missing}")

    if "is_laundering" in event:
        raise RuntimeError(
            "Ground-truth field is_laundering appeared in the online event payload."
        )

    ts = str(event["event_ts"])
    if "T" not in ts and " " in ts:
        ts = ts.replace(" ", "T", 1)

    return {
        "transaction_id": str(event["transaction_id"]),
        "event_ts": ts,
        "from_account_key": account_key(event["from_bank"], event["from_account"]),
        "to_account_key": account_key(event["to_bank"], event["to_account"]),
        "from_bank": str(event["from_bank"]),
        "to_bank": str(event["to_bank"]),
        "amount_paid": float(event["amount_paid"]),
        "amount_received": float(event["amount_received"]),
        "payment_currency": str(event["payment_currency"]),
        "receiving_currency": str(event["receiving_currency"]),
        "payment_format": str(event["payment_format"]),
        "source_row_number": int(event["source_row_number"]),
    }


def apply_batch(tx, rows: list[dict]) -> dict:
    record = tx.run(
        """
        UNWIND $rows AS row

        MERGE (src:Account {account_id: row.from_account_key})
        ON CREATE SET
            src.bank_id = row.from_bank,
            src.created_by_online_graph = true

        MERGE (dst:Account {account_id: row.to_account_key})
        ON CREATE SET
            dst.bank_id = row.to_bank,
            dst.created_by_online_graph = true

        MERGE (src)-[t:TRANSFER {transaction_id: row.transaction_id}]->(dst)
        ON CREATE SET
            t.event_ts = datetime(row.event_ts),
            t.amount_paid = row.amount_paid,
            t.amount_received = row.amount_received,
            t.payment_currency = row.payment_currency,
            t.receiving_currency = row.receiving_currency,
            t.payment_format = row.payment_format,
            t.source_row_number = row.source_row_number

        WITH src, dst, t, row,
             t.online_processed_version IS NULL AS apply_online

        FOREACH (_ IN CASE WHEN apply_online THEN [1] ELSE [] END |
            SET
                src.online_outgoing_tx_count =
                    coalesce(src.online_outgoing_tx_count, 0) + 1,
                src.online_outgoing_amount_paid =
                    coalesce(src.online_outgoing_amount_paid, 0.0) + row.amount_paid,
                src.online_first_outgoing_ts =
                    CASE
                        WHEN src.online_first_outgoing_ts IS NULL
                          OR datetime(row.event_ts) < src.online_first_outgoing_ts
                        THEN datetime(row.event_ts)
                        ELSE src.online_first_outgoing_ts
                    END,
                src.online_last_outgoing_ts =
                    CASE
                        WHEN src.online_last_outgoing_ts IS NULL
                          OR datetime(row.event_ts) > src.online_last_outgoing_ts
                        THEN datetime(row.event_ts)
                        ELSE src.online_last_outgoing_ts
                    END,
                src.online_graph_version = $version
        )

        FOREACH (_ IN CASE WHEN apply_online THEN [1] ELSE [] END |
            SET
                dst.online_incoming_tx_count =
                    coalesce(dst.online_incoming_tx_count, 0) + 1,
                dst.online_incoming_amount_received =
                    coalesce(dst.online_incoming_amount_received, 0.0) + row.amount_received,
                dst.online_first_incoming_ts =
                    CASE
                        WHEN dst.online_first_incoming_ts IS NULL
                          OR datetime(row.event_ts) < dst.online_first_incoming_ts
                        THEN datetime(row.event_ts)
                        ELSE dst.online_first_incoming_ts
                    END,
                dst.online_last_incoming_ts =
                    CASE
                        WHEN dst.online_last_incoming_ts IS NULL
                          OR datetime(row.event_ts) > dst.online_last_incoming_ts
                        THEN datetime(row.event_ts)
                        ELSE dst.online_last_incoming_ts
                    END,
                dst.online_graph_version = $version
        )

        FOREACH (_ IN CASE WHEN apply_online THEN [1] ELSE [] END |
            MERGE (src)-[cp:COUNTERPARTY_STATE {online_version: $version}]->(dst)
            ON CREATE SET
                cp.tx_count = 0,
                cp.total_amount_paid = 0.0,
                cp.total_amount_received = 0.0,
                cp.first_event_ts = datetime(row.event_ts),
                cp.last_event_ts = datetime(row.event_ts)
            SET
                cp.tx_count = cp.tx_count + 1,
                cp.total_amount_paid = cp.total_amount_paid + row.amount_paid,
                cp.total_amount_received = cp.total_amount_received + row.amount_received,
                cp.first_event_ts =
                    CASE
                        WHEN datetime(row.event_ts) < cp.first_event_ts
                        THEN datetime(row.event_ts)
                        ELSE cp.first_event_ts
                    END,
                cp.last_event_ts =
                    CASE
                        WHEN datetime(row.event_ts) > cp.last_event_ts
                        THEN datetime(row.event_ts)
                        ELSE cp.last_event_ts
                    END
        )

        SET
            t.online_processed_version =
                CASE
                    WHEN apply_online THEN $version
                    ELSE t.online_processed_version
                END,
            t.online_source_row_number =
                CASE
                    WHEN apply_online THEN row.source_row_number
                    ELSE t.online_source_row_number
                END

        RETURN
            count(*) AS matched_rows,
            sum(CASE WHEN apply_online THEN 1 ELSE 0 END) AS newly_applied_rows
        """,
        rows=rows,
        version=ONLINE_VERSION,
    ).single()

    return {
        "matched": int(record["matched_rows"]),
        "applied": int(record["newly_applied_rows"]),
    }


def commit_offsets(consumer: Consumer, messages) -> None:
    highest: dict[tuple[str, int], int] = {}
    for msg in messages:
        key = (msg.topic(), msg.partition())
        next_offset = msg.offset() + 1
        highest[key] = max(highest.get(key, 0), next_offset)

    offsets = [
        TopicPartition(topic, partition, offset)
        for (topic, partition), offset in highest.items()
    ]

    if offsets:
        consumer.commit(offsets=offsets, asynchronous=False)


def write_report(
    *,
    topic: str,
    group_id: str,
    received: int,
    applied: int,
    duplicates: int,
    started: float,
    status: str,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "status": status,
        "phase": 9,
        "step": "6A",
        "version": ONLINE_VERSION,
        "topic": topic,
        "consumer_group": group_id,
        "events_received": received,
        "events_newly_applied": applied,
        "duplicate_events_safely_ignored": duplicates,
        "labels_used": False,
        "kafka_auto_commit": False,
        "neo4j_before_kafka_offset_commit": True,
        "idempotency_marker": "TRANSFER.online_processed_version",
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--topic", default=None)
    parser.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument(
        "--offset-reset",
        choices=["earliest", "latest"],
        default="earliest",
    )
    args = parser.parse_args()

    if args.batch_size < 1 or args.batch_size > 1000:
        raise ValueError("--batch-size must be between 1 and 1000.")

    config = load_config(Path(args.config))
    bootstrap = str(config["bootstrap_servers"])
    topic = args.topic or str(config["topic"])

    uri, user, password = resolve_neo4j()

    print("=" * 88)
    print("GraphShield AML - Phase 9 - Online Graph Consumer v1")
    print("=" * 88)
    print(f"KAFKA_BOOTSTRAP={bootstrap}")
    print(f"TOPIC={topic}")
    print(f"GROUP_ID={args.group_id}")
    print(f"BATCH_SIZE={args.batch_size}")
    print(f"MAX_EVENTS={args.max_events or 'continuous'}")
    print(f"NEO4J_URI={uri}")
    print(f"NEO4J_USER={user}")
    print("NEO4J_PASSWORD=<redacted>")
    print("LABEL_FIELD_ALLOWED=FALSE")

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": args.group_id,
            "enable.auto.commit": False,
            "auto.offset.reset": args.offset_reset,
            "client.id": "graphshield-online-graph-v1",
        }
    )

    driver = GraphDatabase.driver(uri, auth=(user, password))

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    received = 0
    applied = 0
    duplicates = 0
    started = time.perf_counter()
    status = "STOPPED"

    try:
        driver.verify_connectivity()
        consumer.subscribe([topic])

        with driver.session(database="neo4j") as session:
            while not STOP_REQUESTED:
                remaining = (
                    args.max_events - received
                    if args.max_events > 0
                    else args.batch_size
                )

                if args.max_events > 0 and remaining <= 0:
                    status = "PASS"
                    break

                wanted = min(args.batch_size, remaining)
                messages = consumer.consume(num_messages=wanted, timeout=2.0)

                usable = []
                rows = []

                for msg in messages:
                    if msg is None:
                        continue
                    if msg.error():
                        if msg.error().code() == KafkaError._PARTITION_EOF:
                            continue
                        raise RuntimeError(f"Kafka consumer error: {msg.error()}")

                    rows.append(normalize_event(msg.value()))
                    usable.append(msg)

                if not rows:
                    continue

                result = session.execute_write(apply_batch, rows)

                if result["matched"] != len(rows):
                    raise RuntimeError(
                        "Neo4j online batch mismatch: "
                        f"expected={len(rows)}, matched={result['matched']}"
                    )

                commit_offsets(consumer, usable)

                received += len(rows)
                applied += result["applied"]
                duplicates += len(rows) - result["applied"]

                print(
                    f"ONLINE_RECEIVED={received:,} "
                    f"NEWLY_APPLIED={applied:,} "
                    f"DUPLICATES_IGNORED={duplicates:,}"
                )

                if args.max_events > 0 and received >= args.max_events:
                    status = "PASS"
                    break

    finally:
        consumer.close()
        driver.close()
        write_report(
            topic=topic,
            group_id=args.group_id,
            received=received,
            applied=applied,
            duplicates=duplicates,
            started=started,
            status=status,
        )

    print(f"EVENTS_RECEIVED={received:,}")
    print(f"EVENTS_NEWLY_APPLIED={applied:,}")
    print(f"DUPLICATES_SAFELY_IGNORED={duplicates:,}")
    print(f"REPORT={REPORT_PATH}")
    print("LABEL_LEAKAGE=NONE")

    if status == "PASS":
        print("GRAPHSHIELD_PHASE9_STEP6A=PASS")
    else:
        print("GRAPHSHIELD_PHASE9_STEP6A=STOPPED")


if __name__ == "__main__":
    main()
