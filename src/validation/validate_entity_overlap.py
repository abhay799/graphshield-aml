from pathlib import Path
import sys

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_CANDIDATES = [
    PROJECT_ROOT / "data" / "processed" / "gold" / "model_features_v1_split.parquet",
    PROJECT_ROOT / "data" / "processed" / "gold" / "model_features_v2_graph_split.parquet",
]

REPORT_DIR = PROJECT_ROOT / "reports" / "modeling"

REPORT_PATH = REPORT_DIR / "phase2_entity_overlap_audit.csv"

REQUIRED_COLUMNS = [
    "split",
    "event_ts",
    "from_account_key",
    "to_account_key",
]


def resolve_input_path() -> Path:
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path

    print("\nERROR: No split model dataset was found.")
    print("\nChecked:")
    for path in INPUT_CANDIDATES:
        print(f"  - {path}")

    sys.exit(1)


def collect_scalar(lf: pl.LazyFrame, column_name: str) -> int:
    result = lf.collect()
    value = result.item(0, column_name)
    return int(value or 0)


def main() -> None:
    print("=" * 88)
    print("GraphShield AML - Phase 2 Entity / Pair Generalisation Audit")
    print("=" * 88)

    input_path = resolve_input_path()

    print("\nInput:")
    print(input_path)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    lf = (
        pl.scan_parquet(input_path)
        .with_columns(
            pl.col("split")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_lowercase()
            .alias("split_normalized")
        )
    )

    schema = lf.collect_schema()
    available_columns = schema.names()

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in available_columns
    ]

    if missing_columns:
        print("\nERROR: Required columns are missing:")
        for column in missing_columns:
            print(f"  - {column}")
        sys.exit(1)

    available_splits = (
        lf.select("split_normalized")
        .unique()
        .sort("split_normalized")
        .collect()
        .get_column("split_normalized")
        .to_list()
    )

    print("\nAvailable splits:")
    print(available_splits)

    if "train" not in available_splits:
        print("\nERROR: No 'train' split was found.")
        sys.exit(1)

    evaluation_splits = [
        split
        for split in ["validation", "valid", "val", "test"]
        if split in available_splits
    ]

    if not evaluation_splits:
        print("\nERROR: No validation or test split was found.")
        sys.exit(1)

    train = lf.filter(pl.col("split_normalized") == "train")

    # One unique account universe from both sender and receiver accounts.
    train_accounts = (
        pl.concat(
            [
                train.select(
                    pl.col("from_account_key").alias("account_key")
                ),
                train.select(
                    pl.col("to_account_key").alias("account_key")
                ),
            ]
        )
        .drop_nulls()
        .unique()
    )

    train_pairs = (
        train.select(
            [
                "from_account_key",
                "to_account_key",
            ]
        )
        .drop_nulls()
        .unique()
    )

    train_transaction_count = collect_scalar(
        train.select(pl.len().alias("value")),
        "value",
    )

    train_account_count = collect_scalar(
        train_accounts.select(pl.len().alias("value")),
        "value",
    )

    train_pair_count = collect_scalar(
        train_pairs.select(pl.len().alias("value")),
        "value",
    )

    print("\n--- TRAIN UNIVERSE ---")
    print(f"Train transactions: {train_transaction_count:,}")
    print(f"Train unique accounts: {train_account_count:,}")
    print(f"Train unique directed pairs: {train_pair_count:,}")

    report_rows = []

    for split_name in evaluation_splits:
        print(f"\n--- AUDITING {split_name.upper()} ---")

        split_lf = lf.filter(
            pl.col("split_normalized") == split_name
        )

        transaction_count = collect_scalar(
            split_lf.select(pl.len().alias("value")),
            "value",
        )

        split_accounts = (
            pl.concat(
                [
                    split_lf.select(
                        pl.col("from_account_key").alias("account_key")
                    ),
                    split_lf.select(
                        pl.col("to_account_key").alias("account_key")
                    ),
                ]
            )
            .drop_nulls()
            .unique()
        )

        unseen_accounts = (
            split_accounts.join(
                train_accounts,
                on="account_key",
                how="anti",
            )
        )

        split_pairs = (
            split_lf.select(
                [
                    "from_account_key",
                    "to_account_key",
                ]
            )
            .drop_nulls()
            .unique()
        )

        new_pairs = (
            split_pairs.join(
                train_pairs,
                on=[
                    "from_account_key",
                    "to_account_key",
                ],
                how="anti",
            )
        )

        split_account_count = collect_scalar(
            split_accounts.select(pl.len().alias("value")),
            "value",
        )

        unseen_account_count = collect_scalar(
            unseen_accounts.select(pl.len().alias("value")),
            "value",
        )

        split_pair_count = collect_scalar(
            split_pairs.select(pl.len().alias("value")),
            "value",
        )

        new_pair_count = collect_scalar(
            new_pairs.select(pl.len().alias("value")),
            "value",
        )

        unseen_account_rate = (
            100 * unseen_account_count / split_account_count
            if split_account_count else 0.0
        )

        new_pair_rate = (
            100 * new_pair_count / split_pair_count
            if split_pair_count else 0.0
        )

        print(f"Transactions: {transaction_count:,}")
        print(f"Unique accounts: {split_account_count:,}")
        print(
            f"Unseen accounts: {unseen_account_count:,} "
            f"({unseen_account_rate:.2f}%)"
        )
        print(f"Unique directed pairs: {split_pair_count:,}")
        print(
            f"New directed pairs: {new_pair_count:,} "
            f"({new_pair_rate:.2f}%)"
        )

        report_rows.append(
            {
                "split": split_name,
                "transactions": transaction_count,
                "unique_accounts": split_account_count,
                "unseen_accounts_vs_train": unseen_account_count,
                "unseen_account_rate_pct": round(
                    unseen_account_rate, 4
                ),
                "unique_directed_pairs": split_pair_count,
                "new_directed_pairs_vs_train": new_pair_count,
                "new_pair_rate_pct": round(new_pair_rate, 4),
            }
        )

    report = pl.DataFrame(report_rows)

    report.write_csv(REPORT_PATH)

    print("\n--- REPORT CREATED ---")
    print(REPORT_PATH)
    print("\n" + "=" * 88)
    print("PHASE 2 ENTITY / PAIR GENERALISATION AUDIT: PASS")
    print("=" * 88)


if __name__ == "__main__":
    main()