from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

SUBGRAPH_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraphs"
)

CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


SOURCE_CANDIDATES = [
    "from_account_key",
    "sender_account_key",
    "sender_account",
    "source_account",
    "src_account",
    "from_account",
    "src_entity_id",
    "Account",
]

TARGET_CANDIDATES = [
    "to_account_key",
    "receiver_account_key",
    "receiver_account",
    "target_account",
    "dst_account",
    "to_account",
    "dst_entity_id",
    "Account_duplicated_0",
]

TX_CANDIDATES = [
    "transaction_id",
    "tx_id",
]

AMOUNT_CANDIDATES = [
    "amount_paid",
    "amount_received",
    "amount_usd",
    "amount",
    "payment_amount",
    "Amount Paid",
]

TIME_CANDIDATES = [
    "event_ts",
    "timestamp",
    "transaction_ts",
]


def first_existing(
    columns: list[str],
    candidates: list[str],
) -> str | None:

    for name in candidates:

        if name in columns:
            return name

    return None


def json_value(
    value: Any,
) -> Any:

    if value is None:
        return None

    if hasattr(value, "isoformat"):

        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    return str(value)


class CaseGraphService:
    """
    Read-only Phase 7 graph-view adapter.

    Reads certified/materialized Phase 6 subgraphs.
    Never rewrites Phase 1-6 artifacts.
    """

    def __init__(self) -> None:

        if not CASE_QUEUE_PATH.exists():

            raise FileNotFoundError(
                f"Case queue missing: "
                f"{CASE_QUEUE_PATH}"
            )

        self._queue = (
            pl.read_parquet(
                CASE_QUEUE_PATH
            )
            .select(
                [
                    column
                    for column
                    in [
                        "case_id",
                        "transaction_id",
                        "risk_rank",
                        "risk_score",
                    ]
                    if column
                    in pl.read_parquet(
                        CASE_QUEUE_PATH,
                        n_rows=1,
                    ).columns
                ]
            )
        )


    def _case_metadata(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        row = (
            self._queue
            .filter(
                pl.col("case_id")
                == case_id
            )
        )

        if row.height == 0:

            raise KeyError(
                f"Unknown case_id: {case_id}"
            )

        return row.row(
            0,
            named=True,
        )


    def get_graph(
        self,
        case_id: str,
        max_edges: int = 250,
    ) -> dict[str, Any]:

        metadata = (
            self._case_metadata(
                case_id
            )
        )

        max_edges = max(
            1,
            min(
                int(max_edges),
                1000,
            ),
        )

        path = (
            SUBGRAPH_DIR
            / f"{case_id}.parquet"
        )

        if not path.exists():

            raise FileNotFoundError(
                (
                    "Case graph is not eagerly "
                    "materialized for this case."
                )
            )

        frame = pl.read_parquet(
            path
        )

        if frame.height == 0:

            raise ValueError(
                "Materialized case subgraph is empty"
            )

        columns = frame.columns

        source_col = first_existing(
            columns,
            SOURCE_CANDIDATES,
        )

        target_col = first_existing(
            columns,
            TARGET_CANDIDATES,
        )

        tx_col = first_existing(
            columns,
            TX_CANDIDATES,
        )

        amount_col = first_existing(
            columns,
            AMOUNT_CANDIDATES,
        )

        time_col = first_existing(
            columns,
            TIME_CANDIDATES,
        )


        if (
            source_col is None
            or target_col is None
        ):

            raise ValueError(
                (
                    "Unable to identify source/"
                    "target account columns. "
                    f"Columns: {columns}"
                )
            )


        focal_tx = metadata.get(
            "transaction_id"
        )


        # Keep focal transaction in the displayed graph.
        if (
            tx_col
            and focal_tx is not None
            and tx_col in frame.columns
        ):

            focal_rows = (
                frame.filter(
                    pl.col(tx_col)
                    == focal_tx
                )
            )

            other_rows = (
                frame.filter(
                    pl.col(tx_col)
                    != focal_tx
                )
            )

            if time_col:

                other_rows = (
                    other_rows.sort(
                        time_col,
                        descending=True,
                    )
                )

            display = pl.concat(
                [
                    focal_rows.head(1),
                    other_rows.head(
                        max(
                            0,
                            max_edges - 1,
                        )
                    ),
                ],
                how="vertical_relaxed",
            )

        else:

            display = (
                frame.sort(
                    time_col,
                    descending=True,
                )
                if time_col
                else frame
            ).head(
                max_edges
            )


        degree: dict[str, int] = {}

        edge_records = []


        for row in display.iter_rows(
            named=True
        ):

            source = str(
                row[source_col]
            )

            target = str(
                row[target_col]
            )

            degree[source] = (
                degree.get(
                    source,
                    0,
                )
                + 1
            )

            degree[target] = (
                degree.get(
                    target,
                    0,
                )
                + 1
            )


            transaction_id = (
                row.get(
                    tx_col
                )
                if tx_col
                else None
            )


            edge_records.append(
                {
                    "source":
                        source,

                    "target":
                        target,

                    "transaction_id":
                        json_value(
                            transaction_id
                        ),

                    "amount":
                        json_value(
                            row.get(
                                amount_col
                            )
                            if amount_col
                            else None
                        ),

                    "event_ts":
                        json_value(
                            row.get(
                                time_col
                            )
                            if time_col
                            else None
                        ),

                    "is_focal":
                        bool(
                            focal_tx is not None
                            and transaction_id
                            == focal_tx
                        ),
                }
            )


        focal_accounts = set()

        for edge in edge_records:

            if edge["is_focal"]:

                focal_accounts.add(
                    edge["source"]
                )

                focal_accounts.add(
                    edge["target"]
                )


        nodes = []

        for account in sorted(
            degree
        ):

            nodes.append(
                {
                    "id":
                        account,

                    "label":
                        (
                            account
                            if len(account) <= 18
                            else (
                                account[:8]
                                + "..."
                                + account[-6:]
                            )
                        ),

                    "degree":
                        degree[account],

                    "focal_endpoint":
                        account
                        in focal_accounts,
                }
            )


        return {
            "case_id":
                case_id,

            "materialized":
                True,

            "risk_rank":
                metadata.get(
                    "risk_rank"
                ),

            "risk_score":
                metadata.get(
                    "risk_score"
                ),

            "focal_transaction_id":
                focal_tx,

            "source_column":
                source_col,

            "target_column":
                target_col,

            "total_subgraph_edges":
                frame.height,

            "displayed_edges":
                len(
                    edge_records
                ),

            "displayed_nodes":
                len(
                    nodes
                ),

            "nodes":
                nodes,

            "edges":
                edge_records,
        }
