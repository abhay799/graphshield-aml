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

EDGE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
    / "entity_edges.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraphs"
)

MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraph_manifest.parquet"
)



FIRST_HOP_MAX = 200
SECOND_HOP_MAX = 300


def main():

    print("=" * 90)
    print("GraphShield AML - Case Evidence Subgraphs")
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cases = (
        pl.read_parquet(
            CASE_QUEUE_PATH
        )
        .sort("risk_rank")
        .head(374)
    )

    manifests = []

    for index, case in enumerate(
        cases.iter_rows(
            named=True
        ),
        start=1,
    ):

        case_id = case[
            "case_id"
        ]

        cutoff = case[
            "event_ts"
        ]

        focal_transaction = case[
            "transaction_id"
        ]

        src_entity = case[
            "from_entity_id"
        ]

        dst_entity = case[
            "to_entity_id"
        ]

        seed_entities = [
            src_entity,
            dst_entity,
        ]

        print(
            f"\n[{index}/{cases.height}] "
            f"{case_id}"
        )

        edges = pl.scan_parquet(
            EDGE_PATH
        )

        # ==================================================
        # 1-hop evidence
        # ==================================================

        first_hop = (
            edges
            .filter(
                (
                    (
                    pl.col("event_ts")
                    < pl.lit(cutoff).cast(
                        pl.Datetime("us", "UTC")
                    )
                )
                |
                (
                    pl.col("transaction_id")
                    == pl.lit(focal_transaction)
                )
                )
                &
                (
                    pl.col(
                        "src_entity_id"
                    )
                    .is_in(
                        seed_entities
                    )
                    |
                    pl.col(
                        "dst_entity_id"
                    )
                    .is_in(
                        seed_entities
                    )
                )
            )
            .sort(
                "event_ts",
                descending=True,
            )
            .head(
                FIRST_HOP_MAX
            )
            .collect()
        )

        neighbor_entities = (
            set(
                first_hop[
                    "src_entity_id"
                ].to_list()
            )
            |
            set(
                first_hop[
                    "dst_entity_id"
                ].to_list()
            )
        )

        # ==================================================
        # 2-hop evidence
        # ==================================================

        if neighbor_entities:

            second_hop = (
                edges
                .filter(
                    (
                        (
                    pl.col("event_ts")
                    < pl.lit(cutoff).cast(
                        pl.Datetime("us", "UTC")
                    )
                )
                |
                (
                    pl.col("transaction_id")
                    == pl.lit(focal_transaction)
                )
                    )
                    &
                    (
                        pl.col(
                            "src_entity_id"
                        )
                        .is_in(
                            list(
                                neighbor_entities
                            )
                        )
                        |
                        pl.col(
                            "dst_entity_id"
                        )
                        .is_in(
                            list(
                                neighbor_entities
                            )
                        )
                    )
                )
                .sort(
                    "event_ts",
                    descending=True,
                )
                .head(
                    SECOND_HOP_MAX
                )
                .collect()
            )

        else:

            second_hop = (
                first_hop.head(0)
            )

        combined = (
            pl.concat(
                [
                    first_hop,
                    second_hop,
                ],
                how="vertical_relaxed",
            )
            .unique(
                subset=[
                    "transaction_id"
                ],
                keep="first",
            )
        )

        combined = (
            combined
            .with_columns(
                [
                    pl.when(
                        pl.col(
                            "transaction_id"
                        )
                        == focal_transaction
                    )
                    .then(
                        pl.lit(0)
                    )

                    .when(
                        pl.col(
                            "src_entity_id"
                        )
                        .is_in(
                            seed_entities
                        )
                        |
                        pl.col(
                            "dst_entity_id"
                        )
                        .is_in(
                            seed_entities
                        )
                    )
                    .then(
                        pl.lit(1)
                    )

                    .otherwise(
                        pl.lit(2)
                    )
                    .alias("hop"),

                    pl.lit(
                        case_id
                    )
                    .alias("case_id"),

                    pl.lit(
                        focal_transaction
                    )
                    .alias(
                        "focal_transaction_id"
                    ),

                    pl.lit(
                        cutoff
                    )
                    .alias(
                        "case_event_ts"
                    ),

                    pl.lit(
                        case[
                            "risk_score"
                        ]
                    )
                    .alias(
                        "case_risk_score"
                    ),
                ]
            )
            .sort(
                [
                    "hop",
                    "event_ts",
                ],
                descending=[
                    False,
                    True,
                ],
            )
        )

        output_path = (
            OUTPUT_DIR
            / f"{case_id}.parquet"
        )

        combined.write_parquet(
            output_path,
            compression="zstd",
        )

        node_count = len(
            set(
                combined[
                    "src_entity_id"
                ].to_list()
            )
            |
            set(
                combined[
                    "dst_entity_id"
                ].to_list()
            )
        )

        manifests.append(
            {
                "case_id":
                    case_id,

                "transaction_id":
                    focal_transaction,

                "event_ts":
                    cutoff,

                "risk_score":
                    case[
                        "risk_score"
                    ],

                "node_count":
                    node_count,

                "edge_count":
                    combined.height,

                "from_entity_id":
                    src_entity,

                "to_entity_id":
                    dst_entity,
            }
        )

    pl.DataFrame(
        manifests
    ).write_parquet(
        MANIFEST_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(MANIFEST_PATH)
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
