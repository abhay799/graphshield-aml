from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


GENESIS_HASH = "0" * 64


def _canonical_json(
    value: dict[str, Any],
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash_record(
    record_without_event_hash: dict[str, Any],
) -> str:
    return hashlib.sha256(
        _canonical_json(
            record_without_event_hash
        ).encode("utf-8")
    ).hexdigest()


def _last_record(
    path: Path,
) -> dict[str, Any] | None:
    if not path.exists():
        return None

    last = None

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line in file:
            text = line.strip()

            if text:
                last = json.loads(
                    text
                )

    return last


def append_hash_chained_record(
    path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    previous = _last_record(
        path
    )

    prev_hash = (
        previous.get(
            "event_hash",
            GENESIS_HASH,
        )
        if previous
        else GENESIS_HASH
    )

    record = {
        "prev_hash": prev_hash,
        "payload": payload,
    }

    record["event_hash"] = (
        _hash_record(
            record
        )
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as file:
        file.write(
            _canonical_json(
                record
            )
            + "\n"
        )
        file.flush()
        os.fsync(
            file.fileno()
        )

    return record


def verify_hash_chain(
    path: Path,
) -> dict[str, Any]:
    if not path.exists():
        return {
            "valid": True,
            "record_count": 0,
            "first_invalid_index": None,
        }

    expected_prev = (
        GENESIS_HASH
    )
    count = 0

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for index, line in enumerate(
            file
        ):
            text = line.strip()

            if not text:
                continue

            record = json.loads(
                text
            )

            event_hash = record.get(
                "event_hash"
            )

            candidate = {
                "prev_hash":
                    record.get(
                        "prev_hash"
                    ),
                "payload":
                    record.get(
                        "payload"
                    ),
            }

            recalculated = (
                _hash_record(
                    candidate
                )
            )

            if (
                record.get(
                    "prev_hash"
                )
                != expected_prev
                or event_hash
                != recalculated
            ):
                return {
                    "valid": False,
                    "record_count": count,
                    "first_invalid_index":
                        index,
                }

            expected_prev = (
                event_hash
            )
            count += 1

    return {
        "valid": True,
        "record_count": count,
        "first_invalid_index": None,
    }
