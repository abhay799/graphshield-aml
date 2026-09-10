import json
import polars as pl
from confluent_kafka import Consumer, TopicPartition

TOPIC = "graphshield.transactions.v1"
SOURCE = "data/processed/silver/transactions.parquet"

expected = (
    pl.read_parquet(SOURCE)
    .sort(["event_ts", "source_row_number", "transaction_id"])
    .head(10)
)

expected_ids = set(expected["transaction_id"].to_list())

c = Consumer({
    "bootstrap.servers": "127.0.0.1:19092",
    "group.id": "graphshield-v2-smoke-verifier",
    "enable.auto.commit": False,
})

meta = c.list_topics(TOPIC, timeout=10)
parts = sorted(meta.topics[TOPIC].partitions)

assignments = [TopicPartition(TOPIC, p, 0) for p in parts]
c.assign(assignments)

events = []

while len(events) < 10:
    msg = c.poll(5)
    if msg is None:
        break
    if msg.error():
        raise RuntimeError(msg.error())
    events.append(json.loads(msg.value().decode("utf-8").strip()))

c.close()

ids = [e["transaction_id"] for e in events]

assert len(events) == 10, f"Expected 10 events, got {len(events)}"
assert len(set(ids)) == 10, "Duplicate transaction IDs detected"
assert set(ids) == expected_ids, "Kafka events do not match expected first 10"
assert all("is_laundering" not in e for e in events), "LABEL LEAKAGE DETECTED"
assert all("event_ts" in e for e in events), "Missing event_ts"
assert all("source_row_number" in e for e in events), "Missing source_row_number"

print("EVENTS_VERIFIED=10")
print("UNIQUE_TRANSACTION_IDS=PASS")
print("EXPECTED_EVENT_SET=PASS")
print("LABEL_LEAKAGE=NONE")
print("EVENT_TIME_METADATA=PASS")
print("GRAPHSHIELD_REPLAY_VERIFICATION=PASS")
