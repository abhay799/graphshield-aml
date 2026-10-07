from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from redis.exceptions import LockError

from services.live_scoring_feature_wrapper import FrozenModelFeatureWrapper
from streaming.phase10_b3_online_feature_parity import normalize


class LiveStateConflictError(RuntimeError):
    """Raised when a write would violate forward-only live-state invariants."""


class GuardedLiveStateWriter:
    """Forward-only write guard around the certified Redis feature wrapper.

    The wrapped Engine remains unchanged. This guard owns only runtime metadata
    under the same namespace: a monotonic timestamp watermark and a committed
    transaction-ID registry.
    """

    WATERMARK_SUFFIX = "guard:watermark"
    COMMITTED_IDS_SUFFIX = "guard:committed_ids"
    LOCK_SUFFIX = "guard:write_lock"

    def __init__(self, wrapper: FrozenModelFeatureWrapper, namespace: str) -> None:
        self.wrapper = wrapper
        self.namespace = namespace.rstrip(":")
        self.redis = wrapper.engine.r

    @property
    def watermark_key(self) -> str:
        return f"{self.namespace}:{self.WATERMARK_SUFFIX}"

    @property
    def committed_ids_key(self) -> str:
        return f"{self.namespace}:{self.COMMITTED_IDS_SUFFIX}"

    @property
    def lock_key(self) -> str:
        return f"{self.namespace}:{self.LOCK_SUFFIX}"

    def watermark_ts(self) -> float | None:
        value = self.redis.get(self.watermark_key)
        return float(value) if value is not None else None

    def is_committed(self, transaction_id: str) -> bool:
        return bool(self.redis.sismember(self.committed_ids_key, str(transaction_id)))

    @staticmethod
    def _normalize_group(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        if not events:
            raise ValueError("live state commit group must not be empty")

        normalized = [normalize(dict(event)) for event in events]
        timestamps = {event["_ts"] for event in normalized}
        if len(timestamps) != 1:
            raise ValueError("live state commit group must contain exactly one event_ts")

        transaction_ids = [event["transaction_id"] for event in normalized]
        if len(set(transaction_ids)) != len(transaction_ids):
            raise LiveStateConflictError(
                "duplicate transaction_id appears more than once in the same commit group"
            )
        return normalized

    def _namespace_has_state_without_watermark(self) -> bool:
        for key in self.redis.scan_iter(match=f"{self.namespace}:*", count=100):
            if key == self.lock_key:
                continue
            return True
        return False

    def _validate_locked(self, normalized: Sequence[dict[str, Any]]) -> float:
        group_ts = float(normalized[0]["_ts"])
        watermark = self.watermark_ts()

        if watermark is None and self._namespace_has_state_without_watermark():
            raise LiveStateConflictError(
                "guard metadata missing for nonempty live namespace; "
                "refusing to adopt pre-existing mutable state"
            )

        if watermark is not None and group_ts < watermark:
            raise LiveStateConflictError(
                "event predates current live state frontier "
                f"(event_ts={group_ts}, watermark={watermark})"
            )

        transaction_ids = [event["transaction_id"] for event in normalized]
        if transaction_ids:
            committed = self.redis.smismember(self.committed_ids_key, transaction_ids)
            duplicates = [
                transaction_id
                for transaction_id, exists in zip(
                    transaction_ids, committed, strict=True
                )
                if exists
            ]
            if duplicates:
                raise LiveStateConflictError(
                    "transaction_id already committed in live namespace: "
                    + ", ".join(duplicates)
                )

        return group_ts

    def commit_group(self, events: Sequence[dict[str, Any]]) -> None:
        normalized = self._normalize_group(events)

        lock = self.redis.lock(
            self.lock_key,
            timeout=30,
            blocking_timeout=10,
        )
        try:
            acquired = lock.acquire()
        except LockError as error:
            raise RuntimeError("could not acquire live-state write guard") from error

        if not acquired:
            raise RuntimeError("could not acquire live-state write guard")

        try:
            group_ts = self._validate_locked(normalized)

            # Delegate the actual feature-state mutation to the certified wrapper.
            # The wrapper/Engine is deliberately not modified by Mode A.
            self.wrapper.commit_group(list(events))

            transaction_ids = [event["transaction_id"] for event in normalized]
            pipe = self.redis.pipeline(transaction=True)
            if transaction_ids:
                pipe.sadd(self.committed_ids_key, *transaction_ids)
            pipe.set(self.watermark_key, repr(group_ts))
            pipe.execute()
        finally:
            try:
                lock.release()
            except LockError:
                # If the lock expired after the guarded operation completed,
                # do not mask the scoring result with a cleanup-only failure.
                pass
