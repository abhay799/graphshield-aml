from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

NODE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_nodes.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
)

REGISTRY_PATH = (
    OUTPUT_DIR
    / "entity_registry.parquet"
)

MAP_PATH = (
    OUTPUT_DIR
    / "account_entity_map.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Entity Registry")
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not NODE_PATH.exists():
        print("\nERROR: account_nodes.parquet missing.")
        return

    # ======================================================
    # Conservative entity-resolution baseline
    #
    # No KYC/PII exists in this synthetic dataset.
    # Therefore:
    #
    # one bank + account key = one provisional entity
    #
    # No unsupported cross-account merging.
    # ======================================================

    registry = (
        pl.scan_parquet(NODE_PATH)
        .select(
            [
                "account_key",
                "bank_id",
            ]
        )
        .unique()
        .sort("account_key")
        .with_row_index(
            "entity_index",
            offset=1,
        )
        .with_columns(
            [
                pl.concat_str(
                    [
                        pl.lit("ENT_"),
                        pl.col(
                            "entity_index"
                        ).cast(pl.String),
                    ]
                )
                .alias("entity_id"),

                pl.lit(
                    "exact_account_key"
                )
                .alias(
                    "resolution_method"
                ),

                pl.lit(1.0)
                .alias(
                    "resolution_confidence"
                ),

                pl.lit(
                    "singleton_no_identity_attributes"
                )
                .alias(
                    "resolution_status"
                ),
            ]
        )
        .select(
            [
                "entity_id",

                pl.col("account_key")
                .alias(
                    "primary_account_key"
                ),

                "bank_id",

                "resolution_method",
                "resolution_confidence",
                "resolution_status",
            ]
        )
    )

    print("\nWriting entity registry...")

    registry.sink_parquet(
        REGISTRY_PATH,
        compression="zstd",
    )

    account_map = (
        pl.scan_parquet(
            REGISTRY_PATH
        )
        .select(
            [
                "entity_id",

                pl.col(
                    "primary_account_key"
                )
                .alias("account_key"),

                "bank_id",

                "resolution_method",
                "resolution_confidence",
            ]
        )
    )

    account_map.sink_parquet(
        MAP_PATH,
        compression="zstd",
    )

    summary = (
        pl.scan_parquet(
            REGISTRY_PATH
        )
        .select(
            [
                pl.len()
                .alias("entities"),

                pl.col(
                    "primary_account_key"
                )
                .n_unique()
                .alias("accounts"),

                pl.col("bank_id")
                .n_unique()
                .alias("banks"),
            ]
        )
        .collect()
    )

    print("\n--- ENTITY SUMMARY ---")
    print(summary)

    print("\nCreated:")
    print(REGISTRY_PATH)
    print(MAP_PATH)


if __name__ == "__main__":
    main()