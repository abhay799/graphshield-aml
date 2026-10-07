"""Frozen-model live feature compatibility wrapper.

This module deliberately wraps, rather than modifies, the certified Phase 10 B3
Engine.  It applies only compatibility transformations required for the frozen
model's training semantics.
"""
from __future__ import annotations

from typing import Any, Iterable

from src.streaming.phase10_b3_online_feature_parity import Engine, W24H, normalize


class FrozenModelFeatureWrapper:
    """Expose Engine features with frozen offline-training compatibility fixes."""

    def __init__(self, redis_url: str, namespace: str):
        self.engine = Engine(redis_url, namespace)

    def clear(self) -> int:
        return self.engine.clear()

    def commit_group(self, events: list[dict[str, Any]]) -> None:
        self.engine.commit_group(events)

    @staticmethod
    def _group_inbound_anchors(
        events: Iterable[dict[str, Any]],
    ) -> set[tuple[str, str, float]]:
        """Return sender/currency/timestamp anchors present in the current group."""
        anchors: set[tuple[str, str, float]] = set()
        for raw in events:
            e = normalize(raw)
            anchors.add((e["to_account_key"], e["receiving_currency"], e["_ts"]))
        return anchors

    def _offline_24h_pass_through(
        self,
        raw: dict[str, Any],
        anchors: set[tuple[str, str, float]],
    ) -> dict[str, Any]:
        e = normalize(raw)
        t = e["_ts"]
        sender = e["from_account_key"]
        currency = e["payment_currency"]

        # FROZEN-MODEL COMPATIBILITY:
        # The offline V5 training pipeline first builds a rolling 24h inbound
        # aggregate on inbound event timestamps, then ordinary-joins that table
        # to the current sender on account + currency + EXACT event_ts.  Thus a
        # current outbound row gets no 24h pass-through history unless an inbound
        # row for that sender/currency exists at the exact same timestamp.
        #
        # This intentionally replicates that training-pipeline quirk.  Do not
        # replace this with a true arbitrary-event 24h lookup without retraining
        # and recertifying the frozen model.
        if (sender, currency, t) not in anchors:
            return {
                "sender_recent_inbound_count_24h": 0,
                "sender_recent_inbound_amount_24h": 0.0,
                "sender_last_inbound_ts_24h": None,
            }

        # Polars rolling(..., closed="left") used offline means [t-24h, t):
        # the exact-timestamp inbound row is only the join anchor and is excluded
        # from the aggregate itself.
        members = self.engine.zrange("inbound", (sender, currency), t - W24H, t)
        amount = 0.0
        for member in members:
            _, raw_amount = member.rsplit("|", 1)
            amount += float(raw_amount)

        latest = self.engine.r.zrevrangebyscore(
            self.engine.k("inbound", sender, currency),
            f"({t}",
            t - W24H,
            start=0,
            num=1,
            withscores=True,
        )
        last_ts = float(latest[0][1]) if latest else None

        return {
            "sender_recent_inbound_count_24h": len(members),
            "sender_recent_inbound_amount_24h": amount,
            "sender_last_inbound_ts_24h": last_ts,
        }

    def _adjust(
        self,
        raw: dict[str, Any],
        result: dict[str, Any],
        anchors: set[tuple[str, str, float]],
    ) -> dict[str, Any]:
        compat = self._offline_24h_pass_through(raw, anchors)

        # Only count_24h is part of the frozen 70-feature model contract.
        # amount_24h and last_inbound_ts_24h share the same offline join quirk,
        # but are retained as compatibility metadata rather than injected into
        # the model feature vector.
        result["features"]["sender_recent_inbound_count_24h"] = compat[
            "sender_recent_inbound_count_24h"
        ]
        result["frozen_model_pass_through_compat"] = compat
        return result

    def feature(self, raw: dict[str, Any]) -> dict[str, Any]:
        # Single-event scoring can only observe an exact-timestamp anchor carried
        # by that event.  feature_group() is authoritative when multiple events
        # share event_ts, matching the certified timestamp-grouping discipline.
        anchors = self._group_inbound_anchors([raw])
        return self._adjust(raw, self.engine.feature(raw), anchors)

    def feature_group(
        self, events: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not events:
            return []
        anchors = self._group_inbound_anchors(events)
        base = self.engine.feature_group(events)
        return [
            self._adjust(raw, result, anchors)
            for raw, result in zip(events, base, strict=True)
        ]
