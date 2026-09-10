from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REGISTRY_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
    / "entity_registry.parquet"
)

MAP_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "entities"
    / "account_entity_map.parquet"
)


def main():

    print("=" * 90)
    print("GraphShield AML - Entity Registry Validation")
    print("=" * 90)

    registry = pl.scan_parquet(
        REGISTRY_PATH
    )

    account_map = pl.scan_parquet(
        MAP_PATH
    )

    integrity = (
        registry.select(
            [
                pl.len()
                .alias("rows"),

                pl.col("entity_id")
                .n_unique()
                .alias("unique_entities"),

                pl.col(
                    "primary_account_key"
                )
                .n_unique()
                .alias("unique_accounts"),

                pl.col("entity_id")
                .null_count()
                .alias("null_entity_ids"),

                pl.col(
                    "primary_account_key"
                )
                .null_count()
                .alias("null_accounts"),
            ]
        )
        .collect()
    )

    print("\n--- REGISTRY INTEGRITY ---")
    print(integrity)

    # Account cannot map to multiple entities.
    ambiguous_accounts = (
        account_map
        .group_by("account_key")
        .agg(
            pl.col("entity_id")
            .n_unique()
            .alias("entity_count")
        )
        .filter(
            pl.col("entity_count") > 1
        )
        .select(pl.len())
        .collect()
        .item()
    )

    print(
        "\nAccounts mapped to multiple entities:",
        ambiguous_accounts,
    )

    print("\nExpected:")
    print("  rows == unique_entities == unique_accounts")
    print("  null IDs = 0")
    print("  ambiguous accounts = 0")


if __name__ == "__main__":
    main()