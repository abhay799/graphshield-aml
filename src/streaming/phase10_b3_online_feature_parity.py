from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import redis


ROOT = Path(__file__).resolve().parents[2]

SILVER = ROOT / "data" / "processed" / "silver" / "transactions.parquet"
GOLD = ROOT / "data" / "processed" / "gold" / "model_features_v2_graph_split.parquet"
BASIC_CONTRACT = ROOT / "reports" / "v2" / "phase10" / "basic_online_feature_contract_v1.json"
MODEL_CONTRACT = ROOT / "reports" / "v2" / "phase10" / "live_feature_contract_v1.json"
REPORT = ROOT / "reports" / "v2" / "phase10" / "online_feature_parity_v1_report.json"

W1H = 3600
W24H = 86400
W7D = 604800


def hid(*parts: str) -> str:
    raw = "\x1f".join(str(x) for x in parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def parse_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if "T" not in text and " " in text:
            text = text.replace(" ", "T", 1)
        dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def normalize(event: dict[str, Any]) -> dict[str, Any]:
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
    ]

    missing = [x for x in required if x not in event]
    if missing:
        raise RuntimeError(f"Missing event fields: {missing}")

    if "is_laundering" in event:
        raise RuntimeError("LABEL LEAKAGE: is_laundering in online event.")

    dt = parse_ts(event["event_ts"])
    fb = str(event["from_bank"])
    fa = str(event["from_account"])
    tb = str(event["to_bank"])
    ta = str(event["to_account"])

    return {
        **event,
        "transaction_id": str(event["transaction_id"]),
        "_dt": dt,
        "_ts": float(dt.timestamp()),
        "from_bank": fb,
        "to_bank": tb,
        "from_account_key": f"{fb}::{fa}",
        "to_account_key": f"{tb}::{ta}",
        "amount_paid": float(event["amount_paid"]),
        "amount_received": float(event["amount_received"]),
        "payment_currency": str(event["payment_currency"]),
        "receiving_currency": str(event["receiving_currency"]),
        "payment_format": str(event["payment_format"]),
    }


class Engine:
    def __init__(self, redis_url: str, namespace: str):
        self.r = redis.Redis.from_url(redis_url, decode_responses=True)
        self.r.ping()
        self.ns = namespace.rstrip(":")

        basic = json.loads(BASIC_CONTRACT.read_text(encoding="utf-8"))
        if basic.get("status") != "PASS" or basic.get("label_used") is not False:
            raise RuntimeError("Basic feature contract is not certified PASS.")

        self.contract = dict(basic["resolved"])

    def k(self, family: str, *parts: str) -> str:
        if not parts:
            return f"{self.ns}:{family}"
        return f"{self.ns}:{family}:{hid(*parts)}"

    def clear(self) -> int:
        deleted = 0
        batch = []
        for key in self.r.scan_iter(match=f"{self.ns}:*", count=1000):
            batch.append(key)
            if len(batch) == 1000:
                deleted += int(self.r.delete(*batch))
                batch = []
        if batch:
            deleted += int(self.r.delete(*batch))
        return deleted

    def h(self, family: str, *parts: str) -> dict[str, str]:
        return self.r.hgetall(self.k(family, *parts))

    @staticmethod
    def hi(d: dict[str, str], name: str) -> int:
        return int(d.get(name, "0"))

    @staticmethod
    def hf(d: dict[str, str], name: str) -> float:
        return float(d.get(name, "0"))

    def zcount(self, family: str, parts: tuple[str, ...], start: float, end: float) -> int:
        # Polars closed="left" => [t-window, t)
        return int(self.r.zcount(self.k(family, *parts), start, f"({end}"))

    def zrange(self, family: str, parts: tuple[str, ...], start: float, end: float) -> list[str]:
        return list(self.r.zrangebyscore(self.k(family, *parts), start, f"({end}"))

    def basic(self, e: dict[str, Any]) -> dict[str, Any]:
        dt = e["_dt"]

        if self.contract.get("hour_of_day") != "dt_hour":
            raise RuntimeError("Unexpected hour contract.")
        if self.contract.get("day_of_week") != "iso_monday_1":
            raise RuntimeError("Unexpected weekday contract.")
        if self.contract.get("cross_bank") != "bank_not_equal":
            raise RuntimeError("Unexpected cross_bank contract.")
        if self.contract.get("cross_currency") != "currency_not_equal":
            raise RuntimeError("Unexpected cross_currency contract.")
        if self.contract.get("log_amount_paid") != "polars_log1p":
            raise RuntimeError("Unexpected log_amount_paid contract.")
        if self.contract.get("log_amount_received") != "polars_log1p":
            raise RuntimeError("Unexpected log_amount_received contract.")

        weekend_rule = self.contract.get("is_weekend")
        if weekend_rule == "iso_ge_6":
            weekend = int(dt.isoweekday() >= 6)
        elif weekend_rule == "iso_ge_5":
            weekend = int(dt.isoweekday() >= 5)
        else:
            raise RuntimeError(f"Unexpected weekend contract: {weekend_rule}")

        paid = float(e["amount_paid"])
        received = float(e["amount_received"])
        same_currency = e["payment_currency"] == e["receiving_currency"]

        return {
            "amount_paid": paid,
            "amount_received": received,
            "payment_format": e["payment_format"],
            "payment_currency": e["payment_currency"],
            "receiving_currency": e["receiving_currency"],
            "log_amount_paid": math.log1p(paid),
            "log_amount_received": math.log1p(received),
            "hour_of_day": int(dt.hour),
            "day_of_week": int(dt.isoweekday()),
            "is_weekend": weekend,
            "cross_bank": int(e["from_bank"] != e["to_bank"]),
            "cross_currency": int(not same_currency),
            "same_currency_amount_ratio": (
                received / paid if same_currency and paid > 0 else None
            ),
        }

    def feature(self, raw: dict[str, Any]) -> dict[str, Any]:
        e = normalize(raw)
        t = e["_ts"]
        s = e["from_account_key"]
        d = e["to_account_key"]
        fb = e["from_bank"]
        tb = e["to_bank"]

        f = self.basic(e)

        # Lifetime sender/receiver history.
        sh = self.h("sender_hist", s)
        rh = self.h("receiver_hist", d)

        sc = self.hi(sh, "tx_count")
        ss = self.hf(sh, "amount_sum")
        rc = self.hi(rh, "tx_count")
        rs = self.hf(rh, "amount_sum")

        sp = float(sh["last_ts"]) if "last_ts" in sh else None
        rp = float(rh["last_ts"]) if "last_ts" in rh else None

        f.update(
            {
                "sender_prior_tx_count": sc,
                "sender_prior_amount_sum": ss,
                "sender_prior_amount_avg": ss / sc if sc > 0 else None,
                "sender_seconds_since_previous": t - sp if sp is not None else None,
                "receiver_prior_tx_count": rc,
                "receiver_prior_amount_sum": rs,
                "receiver_prior_amount_avg": rs / rc if rc > 0 else None,
                "receiver_seconds_since_previous": t - rp if rp is not None else None,
            }
        )

        # Rolling transaction counts.
        st = {
            "1h": self.zcount("sender_tx", (s,), t - W1H, t),
            "24h": self.zcount("sender_tx", (s,), t - W24H, t),
            "7d": self.zcount("sender_tx", (s,), t - W7D, t),
        }
        rt = {
            "1h": self.zcount("receiver_tx", (d,), t - W1H, t),
            "24h": self.zcount("receiver_tx", (d,), t - W24H, t),
            "7d": self.zcount("receiver_tx", (d,), t - W7D, t),
        }

        # Rolling unique counterparties: zset member=counterparty, score=latest ts.
        su = {
            "1h": self.zcount("sender_cp", (s,), t - W1H, t),
            "24h": self.zcount("sender_cp", (s,), t - W24H, t),
            "7d": self.zcount("sender_cp", (s,), t - W7D, t),
        }
        ru = {
            "1h": self.zcount("receiver_cp", (d,), t - W1H, t),
            "24h": self.zcount("receiver_cp", (d,), t - W24H, t),
            "7d": self.zcount("receiver_cp", (d,), t - W7D, t),
        }

        f.update(
            {
                "sender_tx_count_1h": st["1h"],
                "sender_tx_count_24h": st["24h"],
                "sender_tx_count_7d": st["7d"],
                "receiver_tx_count_1h": rt["1h"],
                "receiver_tx_count_24h": rt["24h"],
                "receiver_tx_count_7d": rt["7d"],
                "sender_unique_receivers_1h": su["1h"],
                "sender_unique_receivers_24h": su["24h"],
                "sender_unique_receivers_7d": su["7d"],
                "receiver_unique_senders_1h": ru["1h"],
                "receiver_unique_senders_24h": ru["24h"],
                "receiver_unique_senders_7d": ru["7d"],
                "sender_fanout_ratio_1h": su["1h"] / st["1h"] if st["1h"] > 0 else 0.0,
                "sender_fanout_ratio_24h": su["24h"] / st["24h"] if st["24h"] > 0 else 0.0,
                "receiver_fanin_ratio_1h": ru["1h"] / rt["1h"] if rt["1h"] > 0 else 0.0,
                "receiver_fanin_ratio_24h": ru["24h"] / rt["24h"] if rt["24h"] > 0 else 0.0,
            }
        )

        # Directed pair.
        ph = self.h("pair", s, d)
        pc = self.hi(ph, "tx_count")
        ps = self.hf(ph, "amount_sum")
        pp = float(ph["last_ts"]) if "last_ts" in ph else None
        pf = float(ph["first_ts"]) if "first_ts" in ph else t

        f.update(
            {
                "new_receiver_for_sender": int(pc == 0),
                "new_sender_for_receiver": int(pc == 0),
                "pair_prior_tx_count": pc,
                "pair_prior_amount_sum": ps,
                "pair_prior_amount_avg": ps / pc if pc > 0 else None,
                "pair_seconds_since_previous": t - pp if pp is not None else None,
                "pair_relationship_age_seconds": t - pf,
                "pair_share_of_sender_history": pc / sc if sc > 0 else 0.0,
                "pair_share_of_receiver_history": pc / rc if rc > 0 else 0.0,
                "graph_new_pair": int(pc == 0),
                "graph_established_pair": int(pc >= 10),
            }
        )

        # Lifetime degree / bridge.
        spr = int(self.r.scard(self.k("out_neighbors", s)))
        rps = int(self.r.scard(self.k("in_neighbors", d)))
        sps = int(self.r.scard(self.k("in_neighbors", s)))
        rpr = int(self.r.scard(self.k("out_neighbors", d)))

        f.update(
            {
                "sender_prior_unique_receivers": spr,
                "receiver_prior_unique_senders": rps,
                "sender_prior_unique_senders": sps,
                "receiver_prior_unique_receivers": rpr,
                "sender_bridge_degree": min(sps, spr),
                "receiver_bridge_degree": min(rps, rpr),
            }
        )

        # Bank pair.
        bh = self.h("bank_pair", fb, tb)
        bc = self.hi(bh, "tx_count")
        bs = self.hf(bh, "amount_sum")
        sbh = self.h("sender_bank", fb)
        sbc = self.hi(sbh, "tx_count")

        f.update(
            {
                "bank_pair_prior_tx_count": bc,
                "bank_pair_prior_amount_sum": bs,
                "bank_pair_prior_amount_avg": bs / bc if bc > 0 else None,
                "sender_bank_prior_tx_count": sbc,
                "bank_pair_share_of_sender_bank_history": bc / sbc if sbc > 0 else 0.0,
            }
        )

        # Reverse pair / motifs.
        rev = self.h("pair", d, s)
        rvc = self.hi(rev, "tx_count")
        rvs = self.hf(rev, "amount_sum")
        rvp = float(rev["last_ts"]) if "last_ts" in rev else None

        balance = (
            min(pc, rvc) / max(pc, rvc)
            if pc + rvc > 0
            else 0.0
        )

        f.update(
            {
                "reverse_pair_prior_tx_count": rvc,
                "reverse_pair_prior_amount_sum": rvs,
                "reverse_pair_seconds_since_previous": t - rvp if rvp is not None else None,
                "reciprocal_prior_exists": int(rvc > 0),
                "closes_two_node_cycle": int(rvc > 0),
                "directional_history_balance": balance,
            }
        )

        # Pass-through features.
        currency = e["payment_currency"]
        in1 = self.zrange("inbound", (s, currency), t - W1H, t)
        in24 = self.zrange("inbound", (s, currency), t - W24H, t)

        in_amount_1h = 0.0
        for member in in1:
            _, amount = member.rsplit("|", 1)
            in_amount_1h += float(amount)

        latest = self.r.zrevrangebyscore(
            self.k("inbound", s, currency),
            f"({t}",
            t - W1H,
            start=0,
            num=1,
            withscores=True,
        )
        last_in = float(latest[0][1]) if latest else None

        paid = float(e["amount_paid"])
        coverage = min(1.0, in_amount_1h / paid) if paid > 0 else 0.0
        sec_in = t - last_in if last_in is not None else None

        f.update(
            {
                "sender_recent_inbound_count_1h": len(in1),
                "sender_recent_inbound_count_24h": len(in24),
                "recent_inbound_coverage_1h": coverage,
                "seconds_since_last_inbound_1h": sec_in,
                "rapid_pass_through_candidate": int(
                    len(in1) > 0
                    and coverage >= 0.80
                    and sec_in is not None
                    and sec_in <= 3600
                ),
            }
        )

        return {
            "transaction_id": e["transaction_id"],
            "event_ts": e["event_ts"],
            "features": f,
        }

    def feature_group(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not events:
            return []

        normalized = [normalize(x) for x in events]
        timestamps = {x["_ts"] for x in normalized}
        if len(timestamps) != 1:
            raise RuntimeError("feature_group requires one event_ts group.")

        return [self.feature(x) for x in normalized]

    def commit_group(self, events: list[dict[str, Any]]) -> None:
        normalized = [normalize(x) for x in events]
        if not normalized:
            return

        timestamps = {x["_ts"] for x in normalized}
        if len(timestamps) != 1:
            raise RuntimeError("commit_group requires one event_ts group.")

        t = float(normalized[0]["_ts"])

        sender = defaultdict(lambda: [0, 0.0])
        receiver = defaultdict(lambda: [0, 0.0])
        pair = defaultdict(lambda: [0, 0.0])
        bank_pair = defaultdict(lambda: [0, 0.0])
        sender_bank = defaultdict(int)

        pipe = self.r.pipeline(transaction=True)

        for e in normalized:
            txid = e["transaction_id"]
            s = e["from_account_key"]
            d = e["to_account_key"]
            fb = e["from_bank"]
            tb = e["to_bank"]

            sender[s][0] += 1
            sender[s][1] += e["amount_paid"]

            receiver[d][0] += 1
            receiver[d][1] += e["amount_received"]

            pair[(s, d)][0] += 1
            pair[(s, d)][1] += e["amount_paid"]

            bank_pair[(fb, tb)][0] += 1
            bank_pair[(fb, tb)][1] += e["amount_paid"]

            sender_bank[fb] += 1

            pipe.zadd(self.k("sender_tx", s), {txid: t})
            pipe.zadd(self.k("receiver_tx", d), {txid: t})
            pipe.zadd(self.k("sender_cp", s), {d: t})
            pipe.zadd(self.k("receiver_cp", d), {s: t})

            inbound_member = f"{txid}|{e['amount_received']:.17g}"
            pipe.zadd(
                self.k("inbound", d, e["receiving_currency"]),
                {inbound_member: t},
            )

            pipe.sadd(self.k("out_neighbors", s), d)
            pipe.sadd(self.k("in_neighbors", d), s)

        for s, (count, amount) in sender.items():
            key = self.k("sender_hist", s)
            pipe.hincrby(key, "tx_count", int(count))
            pipe.hincrbyfloat(key, "amount_sum", float(amount))
            pipe.hset(key, "last_ts", t)

        for d, (count, amount) in receiver.items():
            key = self.k("receiver_hist", d)
            pipe.hincrby(key, "tx_count", int(count))
            pipe.hincrbyfloat(key, "amount_sum", float(amount))
            pipe.hset(key, "last_ts", t)

        for (s, d), (count, amount) in pair.items():
            key = self.k("pair", s, d)
            first = self.r.hget(key, "first_ts")

            pipe.hincrby(key, "tx_count", int(count))
            pipe.hincrbyfloat(key, "amount_sum", float(amount))
            pipe.hset(key, "last_ts", t)

            if first is None:
                pipe.hset(key, "first_ts", t)

        for (fb, tb), (count, amount) in bank_pair.items():
            key = self.k("bank_pair", fb, tb)
            pipe.hincrby(key, "tx_count", int(count))
            pipe.hincrbyfloat(key, "amount_sum", float(amount))

        for fb, count in sender_bank.items():
            pipe.hincrby(
                self.k("sender_bank", fb),
                "tx_count",
                int(count),
            )

        cutoff_7d = t - W7D
        cutoff_24h = t - W24H

        for s in sender:
            pipe.zremrangebyscore(self.k("sender_tx", s), "-inf", f"({cutoff_7d}")
            pipe.zremrangebyscore(self.k("sender_cp", s), "-inf", f"({cutoff_7d}")

        for d in receiver:
            pipe.zremrangebyscore(self.k("receiver_tx", d), "-inf", f"({cutoff_7d}")
            pipe.zremrangebyscore(self.k("receiver_cp", d), "-inf", f"({cutoff_7d}")

        for d, currency in {
            (e["to_account_key"], e["receiving_currency"])
            for e in normalized
        }:
            pipe.zremrangebyscore(
                self.k("inbound", d, currency),
                "-inf",
                f"({cutoff_24h}",
            )

        pipe.execute()


def missing(x: Any) -> bool:
    return x is None or (
        isinstance(x, float) and math.isnan(x)
    )


def equal(a: Any, b: Any, atol: float, rtol: float) -> tuple[bool, float | None]:
    if missing(a) and missing(b):
        return True, 0.0
    if missing(a) != missing(b):
        return False, None

    if isinstance(a, str) or isinstance(b, str):
        return str(a) == str(b), None

    try:
        af = float(a)
        bf = float(b)
    except (TypeError, ValueError):
        return a == b, None

    diff = abs(af - bf)

    if af.is_integer() and bf.is_integer():
        return af == bf, diff

    return math.isclose(af, bf, abs_tol=atol, rel_tol=rtol), diff


def load_events(rows: int) -> list[dict[str, Any]]:
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

    return (
        pl.scan_parquet(SILVER)
        .select(cols)
        .sort(["event_ts", "source_row_number", "transaction_id"])
        .head(rows)
        .collect()
        .to_dicts()
    )


def timestamp_groups(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups = []
    current = []
    current_ts = None

    for e in events:
        ts = e["event_ts"]
        if current and ts != current_ts:
            groups.append(current)
            current = []
        current.append(e)
        current_ts = ts

    if current:
        groups.append(current)

    return groups


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=5000)
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--namespace", default="gs:p10:parity:v1")
    parser.add_argument("--atol", type=float, default=1e-9)
    parser.add_argument("--rtol", type=float, default=1e-9)
    args = parser.parse_args()

    for path in (SILVER, GOLD, BASIC_CONTRACT, MODEL_CONTRACT):
        if not path.exists():
            raise FileNotFoundError(path)

    model_contract = json.loads(MODEL_CONTRACT.read_text(encoding="utf-8"))

    if model_contract.get("status") != "PASS":
        raise RuntimeError("Live feature contract is not PASS.")
    if model_contract.get("label_like_features"):
        raise RuntimeError("Model contract contains label-like features.")

    features = list(model_contract["model_features"])

    print("=" * 92)
    print("GraphShield AML - Phase 10 - Redis Online Feature Parity v1")
    print("=" * 92)
    print(f"ROWS={args.rows:,}")
    print(f"MODEL_FEATURES={len(features)}")
    print("LABEL_FIELD_SELECTED=FALSE")
    print("TIMESTAMP_GROUPING=STRICT")

    engine = Engine(args.redis_url, args.namespace)
    print(f"PARITY_NAMESPACE_RESET_KEYS={engine.clear()}")

    events = load_events(args.rows)
    ids = [str(x["transaction_id"]) for x in events]

    expected_frame = (
        pl.scan_parquet(GOLD)
        .filter(pl.col("transaction_id").is_in(ids))
        .select(["transaction_id", *features])
        .collect()
    )

    if expected_frame.height != len(set(ids)):
        raise RuntimeError("Gold lookup row-count mismatch.")

    expected = {
        str(row["transaction_id"]): row
        for row in expected_frame.to_dicts()
    }

    groups = timestamp_groups(events)
    print(f"TIMESTAMP_GROUPS={len(groups):,}")

    mismatches = Counter()
    max_diff = defaultdict(float)
    examples = defaultdict(list)

    rows_done = 0
    values_done = 0

    for index, group in enumerate(groups, start=1):
        online_rows = engine.feature_group(group)

        for row in online_rows:
            txid = row["transaction_id"]
            actual = row["features"]
            exp = expected[txid]

            absent = [name for name in features if name not in actual]
            if absent:
                raise RuntimeError(
                    f"Online engine missing required model features: {absent}"
                )

            for name in features:
                ok, diff = equal(
                    actual[name],
                    exp[name],
                    args.atol,
                    args.rtol,
                )

                values_done += 1

                if diff is not None:
                    max_diff[name] = max(max_diff[name], diff)

                if not ok:
                    mismatches[name] += 1
                    if len(examples[name]) < 3:
                        examples[name].append(
                            {
                                "transaction_id": txid,
                                "event_ts": str(row["event_ts"]),
                                "actual": actual[name],
                                "expected": exp[name],
                                "abs_diff": diff,
                            }
                        )

            rows_done += 1

        # Strict PIT: state update occurs only AFTER all rows at this timestamp
        # have been featured and compared.
        engine.commit_group(group)

        if index % 500 == 0:
            print(f"PROGRESS_GROUPS={index:,} ROWS={rows_done:,}")

    total = int(sum(mismatches.values()))
    status = "PASS" if total == 0 else "FAIL"

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "status": status,
                "phase": 10,
                "block": "B3-feature-parity",
                "rows_compared": rows_done,
                "values_compared": values_done,
                "timestamp_groups": len(groups),
                "model_feature_count": len(features),
                "total_mismatches": total,
                "mismatch_counts": dict(mismatches),
                "max_abs_diff": dict(max_diff),
                "examples": dict(examples),
                "strict_timestamp_grouping": True,
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
    print(f"ROWS_COMPARED={rows_done:,}")
    print(f"VALUES_COMPARED={values_done:,}")
    print(f"TOTAL_MISMATCHES={total:,}")

    if mismatches:
        print("\n=== MISMATCHES BY FEATURE ===")
        for name, count in mismatches.most_common():
            print(
                f"{name:<45}{count:>10,} "
                f"MAX_ABS_DIFF={max_diff.get(name, 0.0):.12g}"
            )

    print()
    print("LABEL_LEAKAGE=NONE")
    print("ZERO_FILL_MISSING_FEATURES=FALSE")
    print("CURRENT_TIMESTAMP_STATE_VISIBLE=FALSE")
    print(f"REPORT={REPORT}")

    if status == "PASS":
        print("GRAPHSHIELD_PHASE10_BLOCK_B3_PARITY=PASS")
    else:
        print("GRAPHSHIELD_PHASE10_BLOCK_B3_PARITY=FAIL")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
