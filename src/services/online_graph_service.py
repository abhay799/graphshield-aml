from __future__ import annotations

import os
import subprocess
from typing import Any

from neo4j import GraphDatabase


ONLINE_VERSION = "online_graph_v1"


def _normalise(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(k): _normalise(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]

    if hasattr(value, "iso_format"):
        try:
            return value.iso_format()
        except Exception:
            pass

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return value


def _resolve_auth() -> tuple[str, str]:
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD")

    auth = os.getenv("NEO4J_AUTH")

    if auth and "/" in auth:
        user, password = auth.split("/", 1)

    if password:
        return user, password

    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "graphshield-neo4j",
                "--format",
                "{{range .Config.Env}}{{println .}}{{end}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        for line in result.stdout.splitlines():
            if line.startswith("NEO4J_AUTH="):
                value = line.split("=", 1)[1]

                if "/" not in value:
                    break

                user, password = value.split("/", 1)
                return user, password

    except Exception as error:
        raise RuntimeError(
            "Unable to resolve Neo4j authentication."
        ) from error

    raise RuntimeError(
        "Neo4j authentication is unavailable."
    )


class OnlineGraphService:
    """
    Read-only Phase 9 Neo4j query service.

    No AML labels are returned or used.
    No mutation queries are permitted here.
    """

    def __init__(self) -> None:
        self.uri = os.getenv(
            "NEO4J_URI",
            "bolt://127.0.0.1:7687",
        )

        user, password = _resolve_auth()

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(user, password),
        )

        self.driver.verify_connectivity()

    def _single(
        self,
        query: str,
        **params: Any,
    ) -> dict[str, Any] | None:

        with self.driver.session() as session:
            record = session.run(
                query,
                **params,
            ).single()

        if record is None:
            return None

        return _normalise(dict(record))

    def status(self) -> dict[str, Any]:
        query = """
        MATCH ()-[r:TRANSFER]->()
        WHERE r.online_processed_version = $version
        RETURN
            count(r) AS online_processed_transfers,
            max(r.event_ts) AS latest_event_ts
        """

        transfer_state = self._single(
            query,
            version=ONLINE_VERSION,
        )

        cp_query = """
        MATCH ()-[r:COUNTERPARTY_STATE]->()
        WHERE r.online_version = $version
        RETURN count(r) AS online_counterparty_relationships
        """

        counterparty_state = self._single(
            cp_query,
            version=ONLINE_VERSION,
        )

        return {
            "status": "ok",
            "mode": "read_only",
            "online_version": ONLINE_VERSION,
            "label_exposure": False,
            **(transfer_state or {}),
            **(counterparty_state or {}),
        }

    def account(
        self,
        account_key: str,
    ) -> dict[str, Any]:

        result = self._single(
            """
            MATCH (a:Account {account_key: $account_key})
            RETURN properties(a) AS account
            """,
            account_key=account_key,
        )

        if result is None:
            raise KeyError(
                f"Unknown account_key: {account_key}"
            )

        return result

    def counterparties(
        self,
        account_key: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        self.account(account_key)

        query = """
        MATCH
            (a:Account {account_key: $account_key})
            -[r:COUNTERPARTY_STATE]-
            (b:Account)

        WHERE r.online_version = $version

        RETURN
            b.account_key AS counterparty_account_key,
            properties(b) AS counterparty,
            properties(r) AS online_state,
            CASE
                WHEN startNode(r) = a
                THEN 'outgoing'
                ELSE 'incoming'
            END AS direction

        LIMIT $limit
        """

        with self.driver.session() as session:
            records = session.run(
                query,
                account_key=account_key,
                version=ONLINE_VERSION,
                limit=limit,
            )

            return [
                _normalise(dict(record))
                for record in records
            ]

    def recent_transfers(
        self,
        account_key: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        self.account(account_key)

        query = """
        MATCH
            (a:Account {account_key: $account_key})
            -[r:TRANSFER]-
            (b:Account)

        RETURN
            r.transaction_id AS transaction_id,
            r.event_ts AS event_ts,
            b.account_key AS counterparty_account_key,
            CASE
                WHEN startNode(r) = a
                THEN 'outgoing'
                ELSE 'incoming'
            END AS direction,
            properties(r) AS transfer

        ORDER BY r.event_ts DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            records = session.run(
                query,
                account_key=account_key,
                limit=limit,
            )

            return [
                _normalise(dict(record))
                for record in records
            ]

    def neighborhood(
        self,
        account_key: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:

        self.account(account_key)

        query = """
        MATCH
            (a:Account {account_key: $account_key})
            -[r:TRANSFER]-
            (b:Account)

        WITH
            b,
            count(r) AS transaction_count,
            max(r.event_ts) AS latest_event_ts

        RETURN
            b.account_key AS account_key,
            properties(b) AS account,
            transaction_count,
            latest_event_ts

        ORDER BY transaction_count DESC
        LIMIT $limit
        """

        with self.driver.session() as session:
            records = session.run(
                query,
                account_key=account_key,
                limit=limit,
            )

            return [
                _normalise(dict(record))
                for record in records
            ]