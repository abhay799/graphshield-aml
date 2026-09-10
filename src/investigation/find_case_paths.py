from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)

SUBGRAPH_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraphs"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_paths.jsonl"
)

PROVENANCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_paths_provenance.json"
)

MAX_DEPTH = 3


def to_utc(value):
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def edge_record(row):
    ts = to_utc(
        row["event_ts"]
    )

    return {
        "transaction_id":
            row["transaction_id"],

        "event_ts":
            ts.isoformat(),

        "src_entity_id":
            row["src_entity_id"],

        "dst_entity_id":
            row["dst_entity_id"],

        "from_account_key":
            row.get(
                "from_account_key"
            ),

        "to_account_key":
            row.get(
                "to_account_key"
            ),

        "amount_paid":
            row.get(
                "amount_paid"
            ),

        "payment_currency":
            row.get(
                "payment_currency"
            ),

        "payment_format":
            row.get(
                "payment_format"
            ),
    }


def build_adjacency(
    graph,
    *,
    excluded_pair=None,
):
    adjacency = {}

    rows = (
        graph
        .sort(
            [
                "event_ts",
                "transaction_id",
            ],
            descending=[
                True,
                False,
            ],
        )
        .iter_rows(
            named=True
        )
    )

    for row in rows:
        u = row[
            "src_entity_id"
        ]

        v = row[
            "dst_entity_id"
        ]

        if (
            u is None
            or v is None
        ):
            continue

        if (
            excluded_pair
            is not None
            and (
                u,
                v,
            )
            == excluded_pair
        ):
            continue

        adjacency.setdefault(
            u,
            [],
        ).append(
            (
                v,
                edge_record(row),
            )
        )

    return adjacency


def find_path(
    adjacency,
    start,
    target,
    max_depth,
):
    if (
        start is None
        or target is None
    ):
        return None

    queue = deque(
        [
            (
                start,
                [start],
                [],
            )
        ]
    )

    # Store shallowest depth at which
    # each node has been reached.
    best_depth = {
        start: 0
    }

    while queue:
        (
            node,
            entities,
            supporting_edges,
        ) = queue.popleft()

        depth = len(
            supporting_edges
        )

        if depth >= max_depth:
            continue

        for (
            neighbor,
            edge,
        ) in adjacency.get(
            node,
            [],
        ):
            new_entities = (
                entities
                + [neighbor]
            )

            new_edges = (
                supporting_edges
                + [edge]
            )

            if neighbor == target:
                return {
                    "entities":
                        new_entities,

                    "hop_count":
                        len(
                            new_edges
                        ),

                    "supporting_transactions":
                        new_edges,
                }

            new_depth = len(
                new_edges
            )

            previous_depth = (
                best_depth.get(
                    neighbor
                )
            )

            if (
                previous_depth
                is None
                or new_depth
                < previous_depth
            ):
                best_depth[
                    neighbor
                ] = new_depth

                queue.append(
                    (
                        neighbor,
                        new_entities,
                        new_edges,
                    )
                )

    return None


def validate_path(
    path_result,
    focal_ts,
    focal_tx,
):
    if path_result is None:
        return

    entities = path_result[
        "entities"
    ]

    edges = path_result[
        "supporting_transactions"
    ]

    if (
        len(entities)
        != len(edges) + 1
    ):
        raise RuntimeError(
            "STOP: Invalid entity/edge "
            "path structure"
        )

    if (
        path_result["hop_count"]
        != len(edges)
    ):
        raise RuntimeError(
            "STOP: Invalid path hop count"
        )

    if len(edges) > MAX_DEPTH:
        raise RuntimeError(
            "STOP: Path exceeds MAX_DEPTH"
        )

    for index, edge in enumerate(
        edges
    ):
        tx_id = edge[
            "transaction_id"
        ]

        if tx_id == focal_tx:
            raise RuntimeError(
                "STOP: Focal transaction "
                "appeared inside historical path"
            )

        edge_ts = datetime.fromisoformat(
            edge[
                "event_ts"
            ]
        )

        edge_ts = to_utc(
            edge_ts
        )

        if not (
            edge_ts
            < focal_ts
        ):
            raise RuntimeError(
                "STOP: Path contains "
                "non-prior transaction"
            )

        if (
            edge[
                "src_entity_id"
            ]
            != entities[index]
        ):
            raise RuntimeError(
                "STOP: Path edge source "
                "does not match entity path"
            )

        if (
            edge[
                "dst_entity_id"
            ]
            != entities[
                index + 1
            ]
        ):
            raise RuntimeError(
                "STOP: Path edge destination "
                "does not match entity path"
            )


def main():
    print("=" * 90)

    print(
        "GraphShield AML - "
        "Full Case Relationship Path Evidence"
    )

    print("=" * 90)

    if not CASE_QUEUE_PATH.exists():
        raise FileNotFoundError(
            "STOP: case_queue.parquet missing"
        )

    if not SUBGRAPH_DIR.exists():
        raise FileNotFoundError(
            "STOP: subgraph directory missing"
        )

    cases = (
        pl.read_parquet(
            CASE_QUEUE_PATH
        )
        .sort(
            "risk_rank"
        )
        .head(374)
    )

    if cases.height == 0:
        raise RuntimeError(
            "STOP: Case queue is empty"
        )

    print(
        "\nCases to analyze:",
        cases.height,
    )

    expected_case_ids = set(
        cases[
            "case_id"
        ].to_list()
    )

    subgraph_files = list(
        SUBGRAPH_DIR.glob(
            "*.parquet"
        )
    )

    actual_case_ids = {
        p.stem
        for p in subgraph_files
    }

    missing = sorted(
        expected_case_ids
        - actual_case_ids
    )

    unexpected = sorted(
        actual_case_ids
        - expected_case_ids
    )

    if missing:
        raise RuntimeError(
            "STOP: Missing subgraphs for "
            f"{len(missing)} cases. "
            f"Examples: {missing[:5]}"
        )

    if unexpected:
        raise RuntimeError(
            "STOP: Unexpected/stale subgraphs "
            f"found: {unexpected[:5]}"
        )

    forward_count = 0
    reverse_count = 0
    total_supporting_transactions = 0

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as output:

        for index, case in enumerate(
            cases.iter_rows(
                named=True
            ),
            start=1,
        ):
            case_id = case[
                "case_id"
            ]

            focal_tx = case[
                "transaction_id"
            ]

            focal_ts = to_utc(
                case[
                    "event_ts"
                ]
            )

            src = case[
                "from_entity_id"
            ]

            dst = case[
                "to_entity_id"
            ]

            path = (
                SUBGRAPH_DIR
                / f"{case_id}.parquet"
            )

            graph = pl.read_parquet(
                path
            )

            # Defense in depth:
            # supporting path evidence is ALWAYS
            # strictly earlier than the focal event.
            historical = (
                graph
                .filter(
                    (
                        pl.col(
                            "event_ts"
                        )
                        < pl.lit(
                            focal_ts
                        ).cast(
                            pl.Datetime(
                                "us",
                                "UTC",
                            )
                        )
                    )
                    &
                    (
                        pl.col(
                            "transaction_id"
                        )
                        != pl.lit(
                            focal_tx
                        )
                    )
                )
            )

            # Alternate forward path must not
            # simply reuse a historical direct
            # src -> dst transaction.
            forward_adjacency = (
                build_adjacency(
                    historical,
                    excluded_pair=(
                        src,
                        dst,
                    ),
                )
            )

            # Reverse prior reachability uses
            # every strictly historical edge.
            reverse_adjacency = (
                build_adjacency(
                    historical
                )
            )

            forward_result = find_path(
                forward_adjacency,
                src,
                dst,
                MAX_DEPTH,
            )

            reverse_result = find_path(
                reverse_adjacency,
                dst,
                src,
                MAX_DEPTH,
            )

            validate_path(
                forward_result,
                focal_ts,
                focal_tx,
            )

            validate_path(
                reverse_result,
                focal_ts,
                focal_tx,
            )

            if forward_result:
                forward_count += 1

                total_supporting_transactions += len(
                    forward_result[
                        "supporting_transactions"
                    ]
                )

            if reverse_result:
                reverse_count += 1

                total_supporting_transactions += len(
                    reverse_result[
                        "supporting_transactions"
                    ]
                )

            # Keep old entity-only fields
            # for compatibility with the
            # existing evidence/bundle layer.
            forward_entities = (
                forward_result[
                    "entities"
                ]
                if forward_result
                else None
            )

            reverse_entities = (
                reverse_result[
                    "entities"
                ]
                if reverse_result
                else None
            )

            result = {
                "case_id":
                    case_id,

                "transaction_id":
                    focal_tx,

                "focal_event_ts":
                    focal_ts.isoformat(),

                "alternate_forward_path":
                    forward_entities,

                "reverse_prior_path":
                    reverse_entities,

                "alternate_forward_path_evidence":
                    forward_result,

                "reverse_prior_path_evidence":
                    reverse_result,

                "has_alternate_forward_path":
                    forward_result
                    is not None,

                "closes_multi_hop_cycle":
                    reverse_result
                    is not None,

                "max_search_depth":
                    MAX_DEPTH,

                "supporting_evidence_rule":
                    "event_ts < focal_event_ts",

                "supporting_edges_strictly_prior":
                    True,
            }

            output.write(
                json.dumps(
                    result,
                    ensure_ascii=False,
                )
                + "\n"
            )

            if (
                index % 25 == 0
                or index == cases.height
            ):
                print(
                    f"[{index}/{cases.height}] "
                    "cases analyzed"
                )

    provenance = {
        "cases_expected":
            cases.height,

        "cases_analyzed":
            cases.height,

        "max_search_depth":
            MAX_DEPTH,

        "alternate_forward_paths":
            forward_count,

        "reverse_prior_paths":
            reverse_count,

        "multi_hop_cycle_closures":
            reverse_count,

        "supporting_transactions_recorded":
            total_supporting_transactions,

        "supporting_evidence_rule":
            "event_ts < focal_event_ts",

        "focal_transaction_allowed_as_support":
            False,

        "full_case_coverage":
            True,
    }

    PROVENANCE_PATH.write_text(
        json.dumps(
            provenance,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "Cases analyzed             :",
        cases.height,
    )

    print(
        "Alternate forward paths    :",
        forward_count,
    )

    print(
        "Reverse prior paths        :",
        reverse_count,
    )

    print(
        "Supporting transactions    :",
        total_supporting_transactions,
    )

    print()
    print("Created:")
    print(OUTPUT_PATH)
    print(PROVENANCE_PATH)

    print()
    print(
        "FULL PATH ANALYZER INSTALLATION: PASS"
    )


if __name__ == "__main__":
    main()
