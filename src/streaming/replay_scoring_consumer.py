from __future__ import annotations

import argparse
import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import yaml

from confluent_kafka import (
    Consumer,
    KafkaError,
    Producer,
    TopicPartition,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "v2"
    / "streaming"
    / "replay.yaml"
)

FEATURE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "lightgbm_graph_v1.joblib"
)

CALIBRATOR_PATH = (
    PROJECT_ROOT
    / "models"
    / "probability_calibrator_graph_v1.joblib"
)

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "replay_scoring_consumer_v1_report.json"
)

SCORING_VERSION = "graph_replay_scoring_v1"

DEFAULT_INPUT_TOPIC = "graphshield.transactions.v1"
DEFAULT_OUTPUT_TOPIC = "graphshield.scored-transactions.v1"
DEFAULT_GROUP = "graphshield-replay-scorer-v1"

STOP_REQUESTED = False


def handle_signal(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def logit(probability):
    probability = np.clip(
        probability,
        1e-6,
        1 - 1e-6,
    )

    return np.log(
        probability / (1 - probability)
    )


def load_bootstrap() -> str:
    config = yaml.safe_load(
        CONFIG_PATH.read_text(
            encoding="utf-8"
        )
    )

    return str(
        config["bootstrap_servers"]
    )


def load_runtime():
    if not FEATURE_PATH.exists():
        raise FileNotFoundError(
            FEATURE_PATH
        )

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            MODEL_PATH
        )

    if not CALIBRATOR_PATH.exists():
        raise FileNotFoundError(
            CALIBRATOR_PATH
        )

    model = joblib.load(
        MODEL_PATH
    )

    calibration_bundle = joblib.load(
        CALIBRATOR_PATH
    )

    if (
        calibration_bundle.get("champion")
        != "lightgbm_graph"
    ):
        raise RuntimeError(
            "Wrong calibration artifact."
        )

    feature_names = list(
        calibration_bundle[
            "feature_names"
        ]
    )

    categorical = list(
        calibration_bundle[
            "categorical_features"
        ]
    )

    model_features = list(
        model.feature_name_
    )

    if model_features != feature_names:
        raise RuntimeError(
            "Model/calibrator feature schema mismatch."
        )

    return (
        model,
        calibration_bundle["calibrator"],
        feature_names,
        categorical,
        calibration_bundle[
            "calibration_version"
        ],
    )


def normalize_input(
    payload: bytes,
) -> dict:

    event = json.loads(
        payload.decode("utf-8")
    )

    if "is_laundering" in event:
        raise RuntimeError(
            "Ground-truth label appeared in Kafka input."
        )

    if "transaction_id" not in event:
        raise RuntimeError(
            "transaction_id missing from Kafka event."
        )

    return event


def load_feature_rows(
    transaction_ids: list[str],
    feature_names: list[str],
    categorical: list[str],
) -> pd.DataFrame:

    frame = (
        pl.scan_parquet(
            FEATURE_PATH
        )
        .filter(
            pl.col("transaction_id")
            .is_in(transaction_ids)
        )
        .select(
            [
                "transaction_id",
                *feature_names,
            ]
        )
        .collect()
    )

    if frame.height != len(
        set(transaction_ids)
    ):
        found = set(
            frame.get_column(
                "transaction_id"
            )
            .cast(pl.String)
            .to_list()
        )

        missing = [
            tx
            for tx in transaction_ids
            if tx not in found
        ]

        raise RuntimeError(
            "Certified feature rows missing for: "
            f"{missing[:10]}"
        )

    pdf = frame.to_pandas()

    pdf["transaction_id"] = (
        pdf["transaction_id"]
        .astype(str)
    )

    for column in categorical:
        pdf[column] = (
            pdf[column]
            .astype("category")
        )

    return pdf


def score_events(
    events: list[dict],
    model,
    calibrator,
    feature_names: list[str],
    categorical: list[str],
    calibration_version: str,
) -> list[dict]:

    ids = [
        str(event["transaction_id"])
        for event in events
    ]

    feature_frame = load_feature_rows(
        ids,
        feature_names,
        categorical,
    )

    feature_frame = (
        feature_frame
        .set_index("transaction_id")
        .loc[ids]
        .reset_index()
    )

    X = feature_frame[
        feature_names
    ].copy()

    raw_scores = (
        model.predict_proba(X)[:, 1]
    )

    calibrated_scores = (
        calibrator.predict_proba(
            logit(raw_scores)
            .reshape(-1, 1)
        )[:, 1]
    )

    scored = []

    for event, raw, calibrated in zip(
        events,
        raw_scores,
        calibrated_scores,
    ):

        output = dict(event)

        if "is_laundering" in output:
            raise RuntimeError(
                "Label leakage detected before output."
            )

        output.update(
            {
                "risk_score_raw":
                    float(raw),

                "risk_score_calibrated":
                    float(calibrated),

                "model_name":
                    "lightgbm_graph",

                "model_version":
                    "lightgbm_graph_v1",

                "calibration_version":
                    calibration_version,

                "feature_source":
                    "certified_pit_graph_feature_store",

                "scoring_version":
                    SCORING_VERSION,

                "scored_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

                "decision_support_only":
                    True,
            }
        )

        scored.append(output)

    return scored


def commit_offsets(
    consumer: Consumer,
    messages,
) -> None:

    highest = {}

    for message in messages:
        key = (
            message.topic(),
            message.partition(),
        )

        highest[key] = max(
            highest.get(key, 0),
            message.offset() + 1,
        )

    offsets = [
        TopicPartition(
            topic,
            partition,
            offset,
        )
        for (
            topic,
            partition
        ), offset in highest.items()
    ]

    consumer.commit(
        offsets=offsets,
        asynchronous=False,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input-topic",
        default=DEFAULT_INPUT_TOPIC,
    )

    parser.add_argument(
        "--output-topic",
        default=DEFAULT_OUTPUT_TOPIC,
    )

    parser.add_argument(
        "--group-id",
        default=DEFAULT_GROUP,
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
    )

    parser.add_argument(
        "--max-events",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--offset-reset",
        choices=[
            "earliest",
            "latest",
        ],
        default="earliest",
    )

    args = parser.parse_args()

    bootstrap = load_bootstrap()

    (
        model,
        calibrator,
        feature_names,
        categorical,
        calibration_version,
    ) = load_runtime()

    print("=" * 88)
    print(
        "GraphShield AML - Phase 10 "
        "- Replay Scoring Consumer v1"
    )
    print("=" * 88)

    print(
        f"INPUT_TOPIC={args.input_topic}"
    )

    print(
        f"OUTPUT_TOPIC={args.output_topic}"
    )

    print(
        f"MODEL=lightgbm_graph_v1"
    )

    print(
        f"CALIBRATION={calibration_version}"
    )

    print(
        f"FEATURE_COUNT={len(feature_names)}"
    )

    print(
        "GROUND_TRUTH_ALLOWED=FALSE"
    )

    consumer = Consumer(
        {
            "bootstrap.servers":
                bootstrap,

            "group.id":
                args.group_id,

            "enable.auto.commit":
                False,

            "auto.offset.reset":
                args.offset_reset,

            "client.id":
                "graphshield-phase10-scorer-v1",
        }
    )

    producer = Producer(
        {
            "bootstrap.servers":
                bootstrap,

            "client.id":
                "graphshield-phase10-scored-producer-v1",

            "enable.idempotence":
                True,

            "acks":
                "all",

            "compression.type":
                "zstd",
        }
    )

    signal.signal(
        signal.SIGINT,
        handle_signal,
    )

    signal.signal(
        signal.SIGTERM,
        handle_signal,
    )

    consumer.subscribe(
        [args.input_topic]
    )

    received = 0
    produced = 0

    started = time.perf_counter()

    status = "STOPPED"

    try:

        while not STOP_REQUESTED:

            remaining = (
                args.max_events - received
                if args.max_events > 0
                else args.batch_size
            )

            if (
                args.max_events > 0
                and remaining <= 0
            ):
                status = "PASS"
                break

            wanted = min(
                args.batch_size,
                remaining,
            )

            messages = consumer.consume(
                num_messages=wanted,
                timeout=2.0,
            )

            usable = []
            events = []

            for message in messages:

                if message is None:
                    continue

                if message.error():

                    if (
                        message.error().code()
                        == KafkaError._PARTITION_EOF
                    ):
                        continue

                    raise RuntimeError(
                        f"Kafka error: "
                        f"{message.error()}"
                    )

                events.append(
                    normalize_input(
                        message.value()
                    )
                )

                usable.append(message)

            if not events:
                continue

            scored_events = score_events(
                events,
                model,
                calibrator,
                feature_names,
                categorical,
                calibration_version,
            )

            for event in scored_events:

                if "is_laundering" in event:
                    raise RuntimeError(
                        "Label leakage detected."
                    )

                producer.produce(
                    args.output_topic,
                    key=str(
                        event[
                            "transaction_id"
                        ]
                    ).encode("utf-8"),
                    value=json.dumps(
                        event,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                )

            producer.flush()

            commit_offsets(
                consumer,
                usable,
            )

            received += len(events)
            produced += len(
                scored_events
            )

            print(
                f"RECEIVED={received:,} "
                f"SCORED={produced:,}"
            )

            if (
                args.max_events > 0
                and received
                >= args.max_events
            ):
                status = "PASS"
                break

    finally:

        producer.flush()
        consumer.close()

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = {
        "status": status,
        "phase": 10,
        "block": "A2-A3",
        "input_topic":
            args.input_topic,
        "output_topic":
            args.output_topic,
        "events_received":
            received,
        "events_scored":
            produced,
        "model":
            "lightgbm_graph_v1",
        "calibration_version":
            calibration_version,
        "feature_source":
            "certified_pit_graph_feature_store",
        "labels_used_for_scoring":
            False,
        "decision_support_only":
            True,
        "producer_idempotence":
            True,
        "kafka_auto_commit":
            False,
        "offset_commit_after_scored_publish":
            True,
        "elapsed_seconds":
            round(
                time.perf_counter()
                - started,
                3,
            ),
        "generated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"EVENTS_RECEIVED={received:,}"
    )

    print(
        f"EVENTS_SCORED={produced:,}"
    )

    print(
        "LABEL_LEAKAGE=NONE"
    )

    print(
        "DECISION_SUPPORT_ONLY=TRUE"
    )

    print(
        f"REPORT={REPORT_PATH}"
    )

    if status == "PASS":
        print(
            "GRAPHSHIELD_PHASE10_BLOCK_A=PASS"
        )
    else:
        print(
            "GRAPHSHIELD_PHASE10_BLOCK_A=STOPPED"
        )


if __name__ == "__main__":
    main()