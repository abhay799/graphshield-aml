from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml
from confluent_kafka import Producer


CHECKPOINT_PATH = Path("data/phase7/v2_replay_checkpoint.json")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_checkpoint() -> dict | None:
    if not CHECKPOINT_PATH.exists():
        return None
    return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))


def save_checkpoint(event_ts, source_row_number, transaction_id, sent):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "event_ts": str(event_ts),
        "source_row_number": int(source_row_number),
        "transaction_id": transaction_id,
        "events_sent": int(sent),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    CHECKPOINT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_query(source: str, checkpoint: dict | None, max_events: int | None = None) -> tuple[str, list]:
    columns = """
        transaction_id,
        event_ts,
        from_bank,
        from_account,
        to_bank,
        to_account,
        amount_received,
        receiving_currency,
        amount_paid,
        payment_currency,
        payment_format,
        source_row_number,
        source_dataset
    """

    query = f"""
        SELECT {columns}
        FROM read_parquet(?)
    """
    params = [source]

    if checkpoint:
        query += """
        WHERE
            event_ts > ?
            OR (event_ts = ? AND source_row_number > ?)
            OR (
                event_ts = ?
                AND source_row_number = ?
                AND transaction_id > ?
            )
        """
        ts = datetime.fromisoformat(checkpoint["event_ts"])
        row = checkpoint["source_row_number"]
        txid = checkpoint["transaction_id"]
        params += [ts, ts, row, ts, row, txid]

    query += """
        ORDER BY event_ts, source_row_number, transaction_id
    """

    if max_events is not None:
        query += f" LIMIT {int(max_events)}"

    return query, params


def make_producer(bootstrap_servers: str) -> Producer:
    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "graphshield-v2-replay",
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "zstd",
            "linger.ms": 5,
        }
    )


def serialize_event(columns, row) -> tuple[str, bytes]:
    event = dict(zip(columns, row))

    # Preserve canonical event time in UTC-compatible ISO format.
    if hasattr(event["event_ts"], "isoformat"):
        event["event_ts"] = event["event_ts"].isoformat()

    event["source_row_number"] = int(event["source_row_number"])

    transaction_id = str(event["transaction_id"])

    payload = json.dumps(
        event,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    return transaction_id, payload


def delivery_callback(err, msg):
    if err is not None:
        raise RuntimeError(f"Kafka delivery failed: {err}")


def publish(producer: Producer, topic: str, key: str, payload: bytes):
    while True:
        try:
            producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=payload,
                on_delivery=delivery_callback,
            )
            producer.poll(0)
            return
        except BufferError:
            producer.poll(0.1)


def replay_delay(previous_ts, current_ts, speed_factor: float):
    if previous_ts is None or speed_factor <= 0:
        return

    seconds = (current_ts - previous_ts).total_seconds()
    if seconds > 0:
        time.sleep(seconds / speed_factor)


def run_replay(config: dict, mode: str, resume: bool, max_events: int | None):
    source = config["source"]
    topic = config["topic"]
    bootstrap = config["bootstrap_servers"]
    batch_size = int(config.get("producer_batch_size", 1000))
    checkpoint_every = int(config.get("checkpoint_every", 10000))

    if mode not in config["modes"]:
        raise ValueError(f"Unknown replay mode: {mode}")

    speed_factor = float(config["modes"][mode]["speed_factor"])
    checkpoint = load_checkpoint() if resume else None

    query, params = build_query(source, checkpoint, max_events)

    con = duckdb.connect()
    cursor = con.execute(query, params)
    columns = [d[0] for d in cursor.description]

    producer = make_producer(bootstrap)

    sent = 0
    previously_sent = int(checkpoint.get("events_sent", 0)) if checkpoint else 0
    previous_ts = None
    last_marker = None

    print(f"SOURCE={source}")
    print(f"TOPIC={topic}")
    print(f"MODE={mode}")
    print(f"RESUME={resume}")

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        for row in rows:
            event = dict(zip(columns, row))
            event_ts = event["event_ts"]

            replay_delay(previous_ts, event_ts, speed_factor)

            key, payload = serialize_event(columns, row)
            publish(producer, topic, key, payload)

            previous_ts = event_ts
            sent += 1
            last_marker = (
                event_ts,
                event["source_row_number"],
                event["transaction_id"],
            )

            if sent % checkpoint_every == 0:
                remaining = producer.flush(30)
                if remaining != 0:
                    raise RuntimeError(
                        f"{remaining} Kafka messages were not delivered"
                    )

                save_checkpoint(*last_marker, previously_sent + sent)
                print(f"CHECKPOINT events={sent}")

            if max_events is not None and sent >= max_events:
                break

        if max_events is not None and sent >= max_events:
            break

    remaining = producer.flush(30)
    if remaining != 0:
        raise RuntimeError(f"{remaining} Kafka messages were not delivered")

    if last_marker is not None:
        save_checkpoint(*last_marker, previously_sent + sent)

    con.close()

    print(f"EVENTS_SENT={sent}")
    print("GRAPHSHIELD_REPLAY=PASS")


def main():
    parser = argparse.ArgumentParser(description="GraphShield v2 transaction replay")
    parser.add_argument(
        "--config",
        default="configs/v2/streaming/replay.yaml",
    )
    parser.add_argument(
        "--mode",
        choices=["1x", "10x", "100x", "burst"],
        default="burst",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-events", type=int, default=None)

    args = parser.parse_args()

    config = load_config(args.config)
    run_replay(
        config=config,
        mode=args.mode,
        resume=args.resume,
        max_events=args.max_events,
    )


if __name__ == "__main__":
    main()
