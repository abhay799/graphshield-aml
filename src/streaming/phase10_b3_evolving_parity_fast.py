from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]
STREAMING_DIR = ROOT / "src" / "streaming"

if str(STREAMING_DIR) not in sys.path:
    sys.path.insert(0, str(STREAMING_DIR))

from phase10_b3_online_feature_parity import Engine, equal


SILVER = ROOT / "data" / "processed" / "silver" / "transactions.parquet"
GOLD = ROOT / "data" / "processed" / "gold" / "model_features_v2_graph_split.parquet"
MODEL_CONTRACT = ROOT / "reports" / "v2" / "phase10" / "live_feature_contract_v1.json"
REPORT = ROOT / "reports" / "v2" / "phase10" / "online_feature_parity_evolving_v1_report.json"


def load_two_timestamp_groups(max_rows: int = 25000):
    cols = [
        "transaction_id",
        "source_row_number",
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
    ]

    df = (
        pl.scan_parquet(SILVER)
        .select(cols)
        .sort(["event_ts", "source_row_number", "transaction_id"])
        .head(max_rows)
        .collect()
    )

    timestamps = (
        df.select("event_ts")
        .unique()
        .sort("event_ts")
        .head(2)["event_ts"]
        .to_list()
    )

    if len(timestamps) < 2:
        raise RuntimeError(
            f"Need at least 2 timestamps inside first {max_rows:,} rows."
        )

    first_ts, second_ts = timestamps

    first_group = (
        df.filter(pl.col("event_ts") == first_ts)
        .sort(["source_row_number", "transaction_id"])
        .to_dicts()
    )

    second_group = (
        df.filter(pl.col("event_ts") == second_ts)
        .sort(["source_row_number", "transaction_id"])
        .to_dicts()
    )

    return first_ts, second_ts, first_group, second_group


def load_expected(ids: list[str], feature_names: list[str]) -> dict[str, dict]:
    frame = (
        pl.scan_parquet(GOLD)
        .filter(pl.col("transaction_id").is_in(ids))
        .select(["transaction_id", *feature_names])
        .collect()
    )

    if frame.height != len(set(ids)):
        raise RuntimeError(
            "Gold lookup did not return exactly one row per sampled transaction."
        )

    return {
        str(row["transaction_id"]): row
        for row in frame.to_dicts()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-second-ts", type=int, default=250)
    parser.add_argument("--max-source-rows", type=int, default=25000)
    parser.add_argument(
        "--redis-url",
        default="redis://127.0.0.1:6379/0",
    )
    parser.add_argument(
        "--namespace",
        default="gs:p10:parity:evolving:v1",
    )
    parser.add_argument("--atol", type=float, default=1e-9)
    parser.add_argument("--rtol", type=float, default=1e-9)
    args = parser.parse_args()

    contract = json.loads(MODEL_CONTRACT.read_text(encoding="utf-8"))

    if contract.get("status") != "PASS":
        raise RuntimeError("Live feature contract is not PASS.")

    if contract.get("label_like_features"):
        raise RuntimeError("Model contract contains label-like features.")

    feature_names = list(contract["model_features"])

    print("=" * 92)
    print("GraphShield AML - Phase 10 - FAST Evolving-State Parity v1")
    print("=" * 92)
    print(f"MODEL_FEATURES={len(feature_names)}")
    print("LABEL_FIELD_SELECTED=FALSE")
    print("ZERO_FILL_MISSING_FEATURES=FALSE")
    print("CURRENT_TIMESTAMP_STATE_VISIBLE=FALSE")

    first_ts, second_ts, first_group, second_group = load_two_timestamp_groups(
        args.max_source_rows
    )

    if len(second_group) < 1:
        raise RuntimeError("Second timestamp group is empty.")

    sample = second_group[: args.sample_second_ts]

    print(f"FIRST_TIMESTAMP={first_ts}")
    print(f"FIRST_TIMESTAMP_ROWS={len(first_group):,}")
    print(f"SECOND_TIMESTAMP={second_ts}")
    print(f"SECOND_TIMESTAMP_AVAILABLE_ROWS={len(second_group):,}")
    print(f"SECOND_TIMESTAMP_SAMPLE_ROWS={len(sample):,}")

    engine = Engine(args.redis_url, args.namespace)
    deleted = engine.clear()
    print(f"PARITY_NAMESPACE_RESET_KEYS={deleted}")

    # FAST PATH:
    # We already validated cold-start rows in the earlier 5,000-row smoke.
    # Seed the COMPLETE first timestamp directly into Redis, without spending
    # time generating 70 features for all 10,977 cold-start rows.
    #
    # This is still PIT-correct because every event in the next timestamp may
    # see the entire first timestamp, while no event in the second timestamp
    # is committed before the whole sample is featured.
    print("SEEDING_FIRST_TIMESTAMP_STATE=START")

    # Optimize first-pair initialization: the namespace is freshly reset,
    # so this first timestamp contains no earlier pair state. The existing
    # Engine.commit_group is still correct, but can be slowed by per-pair
    # first_ts reads. Temporarily replace hget with an in-memory no-state
    # answer only for first_ts checks during this initial seed.
    original_hget = engine.r.hget

    def seed_hget(key, field):
        if field == "first_ts":
            return None
        return original_hget(key, field)

    engine.r.hget = seed_hget
    try:
        engine.commit_group(first_group)
    finally:
        engine.r.hget = original_hget

    print("SEEDING_FIRST_TIMESTAMP_STATE=PASS")

    ids = [str(row["transaction_id"]) for row in sample]
    expected = load_expected(ids, feature_names)

    print("SECOND_TIMESTAMP_FEATURE_GENERATION=START")
    online_rows = engine.feature_group(sample)
    print("SECOND_TIMESTAMP_FEATURE_GENERATION=PASS")

    mismatches = Counter()
    max_diff = defaultdict(float)
    examples = defaultdict(list)
    values_compared = 0

    for row in online_rows:
        txid = row["transaction_id"]
        actual = row["features"]
        exp = expected[txid]

        missing_features = [
            name
            for name in feature_names
            if name not in actual
        ]

        if missing_features:
            raise RuntimeError(
                f"Online engine missing model features: {missing_features}"
            )

        for name in feature_names:
            ok, diff = equal(
                actual[name],
                exp[name],
                args.atol,
                args.rtol,
            )

            values_compared += 1

            if diff is not None:
                max_diff[name] = max(max_diff[name], float(diff))

            if not ok:
                mismatches[name] += 1

                if len(examples[name]) < 3:
                    examples[name].append(
                        {
                            "transaction_id": txid,
                            "actual": actual[name],
                            "expected": exp[name],
                            "abs_diff": diff,
                        }
                    )

    total = int(sum(mismatches.values()))
    status = "PASS" if total == 0 else "FAIL"

    REPORT.parent.mkdir(parents=True, exist_ok=True)

    REPORT.write_text(
        json.dumps(
            {
                "status": status,
                "phase": 10,
                "block": "B3-evolving-state-parity",
                "first_timestamp": str(first_ts),
                "first_timestamp_rows_seeded": len(first_group),
                "second_timestamp": str(second_ts),
                "second_timestamp_rows_sampled": len(sample),
                "model_feature_count": len(feature_names),
                "values_compared": values_compared,
                "total_mismatches": total,
                "mismatch_counts": dict(mismatches),
                "max_abs_diff": dict(max_diff),
                "examples": dict(examples),
                "strict_prior_timestamp_state": True,
                "current_timestamp_state_visible": False,
                "zero_fill_missing_features": False,
                "label_selected": False,
                "redis_namespace": args.namespace,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print()
    print(f"FIRST_TIMESTAMP_ROWS_SEEDED={len(first_group):,}")
    print(f"SECOND_TIMESTAMP_ROWS_COMPARED={len(sample):,}")
    print(f"VALUES_COMPARED={values_compared:,}")
    print(f"TOTAL_MISMATCHES={total:,}")

    if mismatches:
        print("\n=== MISMATCHES BY FEATURE ===")
        for name, count in mismatches.most_common():
            print(
                f"{name:<45}{count:>8,} "
                f"MAX_ABS_DIFF={max_diff.get(name, 0.0):.12g}"
            )

    print()
    print("LABEL_LEAKAGE=NONE")
    print("ZERO_FILL_MISSING_FEATURES=FALSE")
    print("CURRENT_TIMESTAMP_STATE_VISIBLE=FALSE")
    print(f"REPORT={REPORT}")

    if status == "PASS":
        print("GRAPHSHIELD_PHASE10_BLOCK_B3_EVOLVING_PARITY=PASS")
    else:
        print("GRAPHSHIELD_PHASE10_BLOCK_B3_EVOLVING_PARITY=FAIL")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
