from pathlib import Path
import hashlib

import polars as pl
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


RAW_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "LI-Small_Trans.csv"
)


SILVER_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)


REGISTRY_PATH = (
    PROJECT_ROOT
    / "data_contracts"
    / "source_registry.yaml"
)


EXPECTED_RAW_COLUMNS = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account_duplicated_0",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]


EXPECTED_SILVER_COLUMNS = [
    "transaction_id",
    "event_ts",

    "from_bank",
    "from_account",

    "to_bank",
    "to_account",

    "amount_received",
    "receiving_currency",

    "amount_paid",
    "payment_currency",

    "payment_format",

    "is_laundering",

    "source_row_number",
    "source_dataset",
]


def calculate_sha256(
    path: Path,
    chunk_size: int = 1024 * 1024,
):

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as file:

        while True:

            chunk = file.read(
                chunk_size
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


def fail_if(
    condition,
    message,
):

    if condition:

        raise RuntimeError(
            message
        )


def main():

    print("=" * 90)
    print("GraphShield AML - Phase 1 Acceptance Validation")
    print("=" * 90)

    # ======================================================
    # FILE EXISTENCE
    # ======================================================

    print(
        "\n--- FILE EXISTENCE ---"
    )

    fail_if(
        not RAW_PATH.exists(),
        f"Raw dataset missing: {RAW_PATH}",
    )

    fail_if(
        not SILVER_PATH.exists(),
        f"Silver dataset missing: {SILVER_PATH}",
    )

    fail_if(
        not REGISTRY_PATH.exists(),
        f"Source registry missing: {REGISTRY_PATH}",
    )

    print("PASS")

    # ======================================================
    # SOURCE REGISTRY
    # ======================================================

    print(
        "\n--- SOURCE PROVENANCE ---"
    )

    with REGISTRY_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:

        registry = yaml.safe_load(
            file
        )

    source = (
        registry[
            "sources"
        ][
            "ibm_li_small"
        ]
    )

    registered_hash = (
        source[
            "provenance"
        ][
            "sha256"
        ]
        .strip()
        .lower()
    )

    fail_if(
        registered_hash
        ==
        "replace_with_actual_sha256",

        "Actual SHA-256 has not been registered.",
    )

    actual_hash = calculate_sha256(
        RAW_PATH
    )

    print(
        "Registered SHA256:",
        registered_hash,
    )

    print(
        "Actual SHA256:    ",
        actual_hash,
    )

    fail_if(
        actual_hash
        != registered_hash,

        "SOURCE HASH MISMATCH. "
        "Raw dataset differs from registered source.",
    )

    print("Hash check: PASS")

    # ======================================================
    # RAW SCHEMA
    # ======================================================

    print(
        "\n--- RAW SCHEMA ---"
    )

    raw_schema = (
        pl.scan_csv(
            RAW_PATH
        )
        .collect_schema()
    )

    raw_columns = list(
        raw_schema.names()
    )

    print(raw_columns)

    fail_if(
        raw_columns
        != EXPECTED_RAW_COLUMNS,

        "Raw schema does not match "
        "the registered IBM LI-Small schema.",
    )

    print("Raw schema: PASS")

    # ======================================================
    # RAW SUMMARY
    # ======================================================

    raw = pl.scan_csv(
        RAW_PATH
    )

    raw_summary = (
        raw.select(
            [
                pl.len()
                .alias(
                    "raw_rows"
                ),

                pl.col(
                    "Is Laundering"
                )
                .sum()
                .alias(
                    "raw_positives"
                ),

                pl.col(
                    "Is Laundering"
                )
                .n_unique()
                .alias(
                    "label_values"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- RAW SUMMARY ---"
    )

    print(raw_summary)

    raw_rows = (
        raw_summary[
            "raw_rows"
        ][0]
    )

    raw_positives = (
        raw_summary[
            "raw_positives"
        ][0]
    )

    # ======================================================
    # SILVER SCHEMA
    # ======================================================

    silver = pl.scan_parquet(
        SILVER_PATH
    )

    silver_schema = (
        silver.collect_schema()
    )

    silver_columns = (
        silver_schema.names()
    )

    missing_columns = [
        column
        for column
        in EXPECTED_SILVER_COLUMNS
        if column
        not in silver_columns
    ]

    print(
        "\n--- SILVER SCHEMA ---"
    )

    print(
        silver_schema
    )

    fail_if(
        len(
            missing_columns
        )
        > 0,

        (
            "Missing Silver columns: "
            + str(
                missing_columns
            )
        ),
    )

    print("Silver schema: PASS")

    # ======================================================
    # SILVER INTEGRITY
    # ======================================================

    integrity = (
        silver.select(
            [
                pl.len()
                .alias(
                    "silver_rows"
                ),

                pl.col(
                    "transaction_id"
                )
                .n_unique()
                .alias(
                    "unique_transaction_ids"
                ),

                pl.col(
                    "source_row_number"
                )
                .n_unique()
                .alias(
                    "unique_source_rows"
                ),

                pl.col(
                    "is_laundering"
                )
                .sum()
                .alias(
                    "silver_positives"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- SILVER INTEGRITY ---"
    )

    print(integrity)

    silver_rows = (
        integrity[
            "silver_rows"
        ][0]
    )

    unique_ids = (
        integrity[
            "unique_transaction_ids"
        ][0]
    )

    unique_source_rows = (
        integrity[
            "unique_source_rows"
        ][0]
    )

    silver_positives = (
        integrity[
            "silver_positives"
        ][0]
    )

    fail_if(
        silver_rows
        != raw_rows,

        (
            "Row-count mismatch: "
            f"raw={raw_rows:,}, "
            f"silver={silver_rows:,}"
        ),
    )

    fail_if(
        unique_ids
        != silver_rows,

        "transaction_id is not unique.",
    )

    fail_if(
        unique_source_rows
        != silver_rows,

        "source_row_number is not unique.",
    )

    fail_if(
        silver_positives
        != raw_positives,

        (
            "Positive-label count changed "
            "between raw and Silver."
        ),
    )

    # ======================================================
    # LABEL VALIDITY
    # ======================================================

    invalid_labels = (
        silver
        .filter(
            ~pl.col(
                "is_laundering"
            )
            .is_in(
                [
                    0,
                    1,
                ]
            )
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        "\nInvalid labels:",
        invalid_labels,
    )

    fail_if(
        invalid_labels > 0,
        "is_laundering contains values outside {0,1}.",
    )

    # ======================================================
    # REQUIRED NULLS
    # ======================================================

    required_columns = [
        "transaction_id",
        "event_ts",

        "from_bank",
        "from_account",

        "to_bank",
        "to_account",

        "amount_paid",
        "amount_received",

        "payment_currency",
        "receiving_currency",

        "payment_format",

        "is_laundering",

        "source_row_number",
        "source_dataset",
    ]

    null_report = (
        silver.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)

                for column
                in required_columns
            ]
        )
        .collect()
    )

    print(
        "\n--- REQUIRED NULL CHECK ---"
    )

    print(null_report)

    total_required_nulls = sum(
        null_report.row(0)
    )

    fail_if(
        total_required_nulls > 0,
        "Required Silver fields contain null values.",
    )

    # ======================================================
    # AMOUNT VALIDITY
    # ======================================================

    amount_checks = (
        silver.select(
            [
                (
                    pl.col(
                        "amount_paid"
                    )
                    < 0
                )
                .sum()
                .alias(
                    "negative_amount_paid"
                ),

                (
                    pl.col(
                        "amount_received"
                    )
                    < 0
                )
                .sum()
                .alias(
                    "negative_amount_received"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- AMOUNT CHECKS ---"
    )

    print(amount_checks)

    fail_if(
        amount_checks[
            "negative_amount_paid"
        ][0]
        > 0,

        "Negative amount_paid values detected.",
    )

    fail_if(
        amount_checks[
            "negative_amount_received"
        ][0]
        > 0,

        "Negative amount_received values detected.",
    )

    # ======================================================
    # STRING VALIDITY
    # ======================================================

    empty_categories = (
        silver.select(
            [
                (
                    pl.col(
                        "payment_currency"
                    )
                    .str.strip_chars()
                    ==
                    ""
                )
                .sum()
                .alias(
                    "empty_payment_currency"
                ),

                (
                    pl.col(
                        "receiving_currency"
                    )
                    .str.strip_chars()
                    ==
                    ""
                )
                .sum()
                .alias(
                    "empty_receiving_currency"
                ),

                (
                    pl.col(
                        "payment_format"
                    )
                    .str.strip_chars()
                    ==
                    ""
                )
                .sum()
                .alias(
                    "empty_payment_format"
                ),
            ]
        )
        .collect()
    )

    print(
        "\n--- CATEGORY CHECKS ---"
    )

    print(empty_categories)

    fail_if(
        sum(
            empty_categories.row(
                0
            )
        )
        > 0,

        "Empty required categorical values detected.",
    )

    # ======================================================
    # TIMESTAMP VALIDITY
    # ======================================================

    timestamp_dtype = (
        silver_schema[
            "event_ts"
        ]
    )

    print(
        "\n--- TIMESTAMP ---"
    )

    print(
        "event_ts dtype:",
        timestamp_dtype,
    )

    invalid_time = (
        silver
        .filter(
            pl.col(
                "event_ts"
            )
            .is_null()
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    fail_if(
        invalid_time > 0,
        "Invalid event timestamps detected.",
    )

    # ======================================================
    # SOURCE DATASET
    # ======================================================

    source_values = (
        silver.select(
            pl.col(
                "source_dataset"
            )
            .unique()
        )
        .collect()
    )

    print(
        "\n--- SOURCE DATASET ---"
    )

    print(source_values)

    fail_if(
        source_values.height
        != 1,

        "Silver contains unexpected multiple source_dataset values.",
    )

    # ======================================================
    # POTENTIAL CONTENT DUPLICATES
    #
    # Report only. Do NOT delete them.
    # ======================================================

    duplicate_columns = [
        "event_ts",

        "from_bank",
        "from_account",

        "to_bank",
        "to_account",

        "amount_received",
        "receiving_currency",

        "amount_paid",
        "payment_currency",

        "payment_format",
        "is_laundering",
    ]

    possible_duplicates = (
        silver
        .group_by(
            duplicate_columns
        )
        .agg(
            pl.len()
            .alias(
                "duplicate_group_size"
            )
        )
        .filter(
            pl.col(
                "duplicate_group_size"
            )
            > 1
        )
        .select(
            (
                pl.col(
                    "duplicate_group_size"
                )
                - 1
            )
            .sum()
            .alias(
                "possible_duplicate_rows"
            )
        )
        .collect()
    )

    possible_duplicate_rows = (
        possible_duplicates[
            "possible_duplicate_rows"
        ][0]
    )

    if possible_duplicate_rows is None:
        possible_duplicate_rows = 0

    print(
        "\nPotential content-duplicate rows:",
        possible_duplicate_rows,
    )

    print(
        "NOTE: These are reported but "
        "not automatically removed."
    )

    # ======================================================
    # FINAL
    # ======================================================

    print(
        "\n" + "=" * 90
    )

    print(
        "PHASE 1 ACCEPTANCE: PASS"
    )

    print("=" * 90)

    print(
        f"Rows:      {silver_rows:,}"
    )

    print(
        f"Positives: {silver_positives:,}"
    )

    print(
        f"Unique IDs:{unique_ids:,}"
    )

    print(
        "Source hash verified."
    )

    print(
        "Canonical schema verified."
    )

    print(
        "Raw → Silver preservation verified."
    )


if __name__ == "__main__":
    main()