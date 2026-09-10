from pathlib import Path
from datetime import datetime, timezone

import hashlib
import json

import duckdb
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BUNDLE_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "bundles"
)

SUBGRAPH_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraphs"
)

DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_store.duckdb"
)

PARQUET_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_documents.parquet"
)

JSONL_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "evidence_documents.jsonl"
)


HISTORY_CHUNK_SIZE = 25


def to_utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def evidence_id(
    case_id,
    source_type,
    source_ref,
):

    raw = (
        f"{case_id}|"
        f"{source_type}|"
        f"{source_ref}"
    )

    digest = (
        hashlib.sha1(
            raw.encode("utf-8")
        )
        .hexdigest()
        [:16]
        .upper()
    )

    return f"EVID_{digest}"


def make_document(
    case_id,
    source_type,
    source_ref,
    content,
    evidence_ts=None,
):

    return {
        "evidence_id":
            evidence_id(
                case_id,
                source_type,
                source_ref,
            ),

        "case_id":
            case_id,

        "source_type":
            source_type,

        "source_ref":
            source_ref,

        "evidence_ts":
            (
                str(evidence_ts)
                if evidence_ts
                is not None
                else None
            ),

        "content":
            content,

        "point_in_time_safe":
            True,
    }


def main():

    print("=" * 90)
    print("GraphShield AML - Evidence Document Builder")
    print("=" * 90)

    bundle_files = sorted(
        BUNDLE_DIR.glob(
            "CASE_*.json"
        )
    )

    if not bundle_files:
        print("\nERROR: No case bundles found.")
        return

    documents = []

    for bundle_path in bundle_files:

        bundle = json.loads(
            bundle_path.read_text(
                encoding="utf-8"
            )
        )

        case = bundle[
            "case_metadata"
        ]

        tx = bundle[
            "focal_transaction"
        ]

        risk = bundle[
            "risk"
        ]

        rules = bundle[
            "rule_evidence"
        ]

        graph = bundle[
            "graph_evidence"
        ]

        case_id = case[
            "case_id"
        ]

        # ==================================================
        # Focal transaction
        # ==================================================

        focal_text = (
            f"Case {case_id} concerns transaction "
            f"{tx['transaction_id']} at "
            f"{tx['event_ts']}. "
            f"The transaction moved "
            f"{tx['amount_paid']} "
            f"{tx['currency']} from entity "
            f"{tx['from_entity_id']} to "
            f"{tx['to_entity_id']} using "
            f"{tx['payment_format']}. "
            f"The prioritization score is "
            f"{risk['score']} from model "
            f"{case['source_model']}."
        )

        documents.append(
            make_document(
                case_id,
                "focal_transaction",
                tx[
                    "transaction_id"
                ],
                focal_text,
                tx[
                    "event_ts"
                ],
            )
        )

        # ==================================================
        # Rules
        # ==================================================

        fired_rules = []

        if rules.get(
            "high_velocity",
            0,
        ):
            fired_rules.append(
                "high velocity"
            )

        if rules.get(
            "rapid_fan_out",
            0,
        ):
            fired_rules.append(
                "rapid fan-out"
            )

        if rules.get(
            "rapid_fan_in",
            0,
        ):
            fired_rules.append(
                "rapid fan-in"
            )

        if rules.get(
            "rapid_pass_through",
            0,
        ):
            fired_rules.append(
                "rapid pass-through"
            )

        if fired_rules:

            rule_text = (
                "Configured deterministic AML "
                "rules triggered for this case: "
                + ", ".join(
                    fired_rules
                )
                + ". "
                + f"Total rule hits: "
                + str(
                    rules.get(
                        "rule_hit_count",
                        len(
                            fired_rules
                        ),
                    )
                )
                + "."
            )

        else:

            rule_text = (
                "No configured deterministic "
                "AML rules triggered for this "
                "focal transaction."
            )

        documents.append(
            make_document(
                case_id,
                "rule_evidence",
                "rules_v1",
                rule_text,
                tx[
                    "event_ts"
                ],
            )
        )

        # ==================================================
        # Graph summary
        # ==================================================

        graph_text = (
            f"The point-in-time investigation "
            f"subgraph for {case_id} contains "
            f"{graph.get('node_count')} entities "
            f"and {graph.get('edge_count')} "
            f"transactions."
        )

        documents.append(
            make_document(
                case_id,
                "graph_summary",
                "subgraph_manifest",
                graph_text,
                tx[
                    "event_ts"
                ],
            )
        )

        # ==================================================
        # Path evidence
        # ==================================================

        forward = graph.get(
            "alternate_forward_path"
        )

        reverse = graph.get(
            "reverse_prior_path"
        )

        path_parts = []

        if forward:

            path_parts.append(
                "A historical alternate directed "
                "path exists between the focal "
                "sender and receiver: "
                + " -> ".join(
                    forward
                )
                + "."
            )

        else:

            path_parts.append(
                "No alternate historical directed "
                "path was found within the "
                "configured search depth."
            )

        if reverse:

            path_parts.append(
                "A historical reverse path exists: "
                + " -> ".join(
                    reverse
                )
                + ". The focal transaction therefore "
                "connects entities with prior reverse "
                "network reachability."
            )

        else:

            path_parts.append(
                "No historical reverse path was "
                "found within the configured depth."
            )

        documents.append(
            make_document(
                case_id,
                "graph_path",
                "case_paths",
                " ".join(
                    path_parts
                ),
                tx[
                    "event_ts"
                ],
            )
        )

        # ==================================================
        # Historical transaction evidence
        # ==================================================

        subgraph_path = (
            SUBGRAPH_DIR
            / f"{case_id}.parquet"
        )

        if subgraph_path.exists():

            focal_ts = to_utc(
                tx[
                    "event_ts"
                ]
            )

            focal_tx = tx[
                "transaction_id"
            ]

            history = (
                pl.read_parquet(
                    subgraph_path
                )
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
                .sort(
                    "event_ts",
                    descending=True,
                )
            )

            # Defense-in-depth validation:
            # historical evidence must never
            # contain the focal transaction or
            # any same-time/future transaction.
            if history.height > 0:

                if (
                    history[
                        "transaction_id"
                    ]
                    == focal_tx
                ).any():
                    raise RuntimeError(
                        "STOP: Historical evidence "
                        f"contains focal tx for {case_id}"
                    )

                latest_history_ts = to_utc(
                    history[
                        "event_ts"
                    ].max()
                )

                if not (
                    latest_history_ts
                    < focal_ts
                ):
                    raise RuntimeError(
                        "STOP: Historical evidence "
                        "is not strictly prior for "
                        f"{case_id}"
                    )

            for chunk_start in range(
                0,
                history.height,
                HISTORY_CHUNK_SIZE,
            ):

                chunk = history.slice(
                    chunk_start,
                    HISTORY_CHUNK_SIZE,
                )

                lines = []

                for row in (
                    chunk.iter_rows(
                        named=True
                    )
                ):

                    lines.append(
                        (
                            f"Transaction "
                            f"{row['transaction_id']} | "
                            f"{row['event_ts']} | "
                            f"{row['src_entity_id']} -> "
                            f"{row['dst_entity_id']} | "
                            f"amount_paid="
                            f"{row['amount_paid']} "
                            f"{row['payment_currency']} | "
                            f"format="
                            f"{row['payment_format']}"
                        )
                    )

                chunk_number = (
                    chunk_start
                    // HISTORY_CHUNK_SIZE
                    + 1
                )

                documents.append(
                    make_document(
                        case_id,
                        "historical_transactions",
                        (
                            f"subgraph_chunk_"
                            f"{chunk_number:03d}"
                        ),
                        "\n".join(
                            lines
                        ),
                        chunk[
                            "event_ts"
                        ].max(),
                    )
                )

    docs = pl.DataFrame(
        documents
    )

    docs.write_parquet(
        PARQUET_PATH,
        compression="zstd",
    )

    with open(
        JSONL_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        for row in docs.iter_rows(
            named=True
        ):

            file.write(
                json.dumps(
                    row,
                    default=str,
                )
                + "\n"
            )

    # ======================================================
    # Update DuckDB case store
    # ======================================================

    con = duckdb.connect(
        str(DB_PATH)
    )

    con.register(
        "evidence_df",
        docs.to_arrow(),
    )
    con.execute(
        """
        CREATE OR REPLACE TABLE evidence_documents AS
        SELECT
            evidence_id,
            case_id,
            source_type,
            source_ref,
            evidence_ts,
            content,
            point_in_time_safe
        FROM evidence_df
        """
    )

    count = (
        con.execute(
            """
            SELECT COUNT(*)
            FROM evidence_documents
            """
        )
        .fetchone()[0]
    )

    con.close()

    print(
        f"\nEvidence documents: "
        f"{count:,}"
    )

    print("\nCreated:")
    print(PARQUET_PATH)
    print(JSONL_PATH)


if __name__ == "__main__":
    main()
