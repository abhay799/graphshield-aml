from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
import uuid


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "phase7"
    / "analyst_workbench.sqlite"
)


ALLOWED_STATUSES = {
    "unreviewed",
    "in_review",
    "needs_more_information",
    "escalated",
    "review_complete",
}


class AnalystStateService:
    """
    Phase 7 operational analyst state.

    Important:
    - Does not modify certified Phase 1-6 artifacts.
    - Audit events are append-only.
    - Analyst decisions remain human actions.
    """

    def __init__(self) -> None:

        DB_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize()


    def _connect(self):

        connection = sqlite3.connect(
            DB_PATH,
            timeout=30,
        )

        connection.row_factory = (
            sqlite3.Row
        )

        connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        return connection


    @staticmethod
    def _utc_now() -> str:

        return (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        )


    def _initialize(self) -> None:

        with self._connect() as connection:

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                analyst_case_state (
                    case_id TEXT PRIMARY KEY,
                    review_status TEXT NOT NULL,
                    analyst_note TEXT,
                    actor TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS
                audit_events (
                    event_id TEXT PRIMARY KEY,
                    event_ts_utc TEXT NOT NULL,
                    case_id TEXT,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_audit_case_time
                ON audit_events(
                    case_id,
                    event_ts_utc
                )
                """
            )


    def append_event(
        self,
        event_type: str,
        actor: str,
        case_id: str | None = None,
        payload: dict | None = None,
    ) -> dict:

        event = {
            "event_id":
                str(uuid.uuid4()),

            "event_ts_utc":
                self._utc_now(),

            "case_id":
                case_id,

            "actor":
                actor.strip()
                or "local_analyst",

            "event_type":
                event_type,

            "payload":
                payload or {},
        }

        with self._connect() as connection:

            connection.execute(
                """
                INSERT INTO audit_events (
                    event_id,
                    event_ts_utc,
                    case_id,
                    actor,
                    event_type,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    event["event_ts_utc"],
                    event["case_id"],
                    event["actor"],
                    event["event_type"],
                    json.dumps(
                        event["payload"],
                        sort_keys=True,
                    ),
                ),
            )

        return event


    def get_case_state(
        self,
        case_id: str,
    ) -> dict:

        with self._connect() as connection:

            row = connection.execute(
                """
                SELECT
                    case_id,
                    review_status,
                    analyst_note,
                    actor,
                    updated_at_utc
                FROM analyst_case_state
                WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()

        if row is None:

            return {
                "case_id":
                    case_id,

                "review_status":
                    "unreviewed",

                "analyst_note":
                    None,

                "actor":
                    None,

                "updated_at_utc":
                    None,
            }

        return dict(row)


    def update_case_state(
        self,
        case_id: str,
        review_status: str,
        analyst_note: str | None,
        actor: str,
    ) -> dict:

        if review_status not in (
            ALLOWED_STATUSES
        ):

            raise ValueError(
                "Invalid review_status. "
                f"Allowed: "
                f"{sorted(ALLOWED_STATUSES)}"
            )

        actor = (
            actor.strip()
            or "local_analyst"
        )

        updated_at = (
            self._utc_now()
        )

        previous = (
            self.get_case_state(
                case_id
            )
        )

        with self._connect() as connection:

            connection.execute(
                """
                INSERT INTO analyst_case_state (
                    case_id,
                    review_status,
                    analyst_note,
                    actor,
                    updated_at_utc
                )
                VALUES (?, ?, ?, ?, ?)

                ON CONFLICT(case_id)
                DO UPDATE SET
                    review_status =
                        excluded.review_status,
                    analyst_note =
                        excluded.analyst_note,
                    actor =
                        excluded.actor,
                    updated_at_utc =
                        excluded.updated_at_utc
                """,
                (
                    case_id,
                    review_status,
                    analyst_note,
                    actor,
                    updated_at,
                ),
            )

        current = {
            "case_id":
                case_id,

            "review_status":
                review_status,

            "analyst_note":
                analyst_note,

            "actor":
                actor,

            "updated_at_utc":
                updated_at,
        }

        self.append_event(
            event_type=
                "case_state_updated",

            actor=
                actor,

            case_id=
                case_id,

            payload={
                "previous":
                    previous,

                "current":
                    current,
            },
        )

        return current


    def case_audit_history(
        self,
        case_id: str,
        limit: int = 100,
    ) -> list[dict]:

        limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        with self._connect() as connection:

            rows = connection.execute(
                """
                SELECT
                    event_id,
                    event_ts_utc,
                    case_id,
                    actor,
                    event_type,
                    payload_json
                FROM audit_events
                WHERE case_id = ?
                ORDER BY event_ts_utc DESC
                LIMIT ?
                """,
                (
                    case_id,
                    limit,
                ),
            ).fetchall()

        results = []

        for row in rows:

            item = dict(row)

            item["payload"] = (
                json.loads(
                    item.pop(
                        "payload_json"
                    )
                )
            )

            results.append(
                item
            )

        return results
