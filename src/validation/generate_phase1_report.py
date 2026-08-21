from pathlib import Path

import polars as pl


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

REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
)

REPORT_PATH = (
    REPORT_DIR
    / "phase1_data_quality_report.md"
)


def main():

    print("=" * 70)
    print("GraphShield AML - Phase 1 Data Quality Report")
    print("=" * 70)

    if not RAW_PATH.exists():
        print("\nERROR: Raw dataset missing.")
        return

    if not SILVER_PATH.exists():
        print("\nERROR: Silver dataset missing.")
        return

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    print("\nScanning datasets...")

    raw = pl.scan_csv(
        RAW_PATH
    )

    silver = pl.scan_parquet(
        SILVER_PATH
    )

    # ==================================================
    # Row counts
    # ==================================================

    raw_rows = (
        raw.select(
            pl.len()
        )
        .collect()
        .item()
    )

    silver_rows = (
        silver.select(
            pl.len()
        )
        .collect()
        .item()
    )

    # ==================================================
    # Label statistics
    # ==================================================

    laundering_count = (
        silver.select(
            pl.col("is_laundering")
            .sum()
        )
        .collect()
        .item()
    )

    legitimate_count = (
        silver_rows
        - laundering_count
    )

    laundering_rate = (
        laundering_count
        / silver_rows
        * 100
    )

    # ==================================================
    # Transaction ID uniqueness
    # ==================================================

    unique_transaction_ids = (
        silver.select(
            pl.col("transaction_id")
            .n_unique()
        )
        .collect()
        .item()
    )

    # ==================================================
    # Timestamp range
    # ==================================================

    time_stats = (
        silver.select(
            [
                pl.col("event_ts")
                .min()
                .alias("earliest"),

                pl.col("event_ts")
                .max()
                .alias("latest"),

                pl.col("event_ts")
                .null_count()
                .alias("null_timestamps"),
            ]
        )
        .collect()
    )

    earliest = time_stats["earliest"][0]
    latest = time_stats["latest"][0]
    null_timestamps = time_stats["null_timestamps"][0]

    # ==================================================
    # Amount quality
    # ==================================================

    amount_quality = (
        silver.select(
            [
                (
                    pl.col("amount_paid") < 0
                )
                .sum()
                .alias("negative_paid"),

                (
                    pl.col("amount_received") < 0
                )
                .sum()
                .alias("negative_received"),

                (
                    pl.col("amount_paid") == 0
                )
                .sum()
                .alias("zero_paid"),

                (
                    pl.col("amount_received") == 0
                )
                .sum()
                .alias("zero_received"),
            ]
        )
        .collect()
    )

    negative_paid = amount_quality[
        "negative_paid"
    ][0]

    negative_received = amount_quality[
        "negative_received"
    ][0]

    zero_paid = amount_quality[
        "zero_paid"
    ][0]

    zero_received = amount_quality[
        "zero_received"
    ][0]

    # ==================================================
    # Critical null checks
    # ==================================================

    critical_columns = [
        "transaction_id",
        "event_ts",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "amount_paid",
        "payment_currency",
        "is_laundering",
    ]

    null_result = (
        silver.select(
            [
                pl.col(column)
                .null_count()
                .alias(column)

                for column
                in critical_columns
            ]
        )
        .collect()
    )

    # ==================================================
    # File sizes
    # ==================================================

    raw_size_mb = (
        RAW_PATH.stat().st_size
        / (1024 * 1024)
    )

    silver_size_mb = (
        SILVER_PATH.stat().st_size
        / (1024 * 1024)
    )

    # ==================================================
    # Generate Markdown
    # ==================================================

    lines = []

    lines.append(
        "# GraphShield AML - Phase 1 Data Quality Report"
    )

    lines.append("")

    lines.append(
        "## Dataset"
    )

    lines.append("")

    lines.append(
        "- Source: IBM AML LI-Small"
    )

    lines.append(
        "- Synthetic dataset: Yes"
    )

    lines.append(
        f"- Raw rows: {raw_rows:,}"
    )

    lines.append(
        f"- Silver rows: {silver_rows:,}"
    )

    lines.append("")

    lines.append(
        "## Row Preservation"
    )

    lines.append("")

    if raw_rows == silver_rows:

        lines.append(
            "PASS - Raw and Silver row counts match."
        )

    else:

        lines.append(
            "FAIL - Row count changed during transformation."
        )

    lines.append("")

    lines.append(
        "## Target Distribution"
    )

    lines.append("")

    lines.append(
        f"- Legitimate transactions: {legitimate_count:,}"
    )

    lines.append(
        f"- Laundering transactions: {laundering_count:,}"
    )

    lines.append(
        f"- Laundering rate: {laundering_rate:.6f}%"
    )

    lines.append("")

    lines.append(
        "## Transaction IDs"
    )

    lines.append("")

    lines.append(
        f"- Rows: {silver_rows:,}"
    )

    lines.append(
        f"- Unique transaction IDs: "
        f"{unique_transaction_ids:,}"
    )

    if (
        unique_transaction_ids
        == silver_rows
    ):

        lines.append(
            "- PASS - Transaction IDs are unique."
        )

    else:

        lines.append(
            "- FAIL - Duplicate transaction IDs exist."
        )

    lines.append("")

    lines.append(
        "## Timestamp Quality"
    )

    lines.append("")

    lines.append(
        f"- Earliest transaction: {earliest}"
    )

    lines.append(
        f"- Latest transaction: {latest}"
    )

    lines.append(
        f"- Null timestamps: {null_timestamps:,}"
    )

    lines.append("")

    lines.append(
        "## Amount Quality"
    )

    lines.append("")

    lines.append(
        f"- Negative amount_paid: "
        f"{negative_paid:,}"
    )

    lines.append(
        f"- Negative amount_received: "
        f"{negative_received:,}"
    )

    lines.append(
        f"- Zero amount_paid: "
        f"{zero_paid:,}"
    )

    lines.append(
        f"- Zero amount_received: "
        f"{zero_received:,}"
    )

    lines.append("")

    lines.append(
        "## Critical Nulls"
    )

    lines.append("")

    for column in critical_columns:

        count = null_result[
            column
        ][0]

        status = (
            "PASS"
            if count == 0
            else "WARNING"
        )

        lines.append(
            f"- {column}: "
            f"{count:,} [{status}]"
        )

    lines.append("")

    lines.append(
        "## Storage"
    )

    lines.append("")

    lines.append(
        f"- Raw CSV: {raw_size_mb:.2f} MB"
    )

    lines.append(
        f"- Silver Parquet: "
        f"{silver_size_mb:.2f} MB"
    )

    if raw_size_mb > 0:

        reduction = (
            (
                raw_size_mb
                - silver_size_mb
            )
            / raw_size_mb
            * 100
        )

        lines.append(
            f"- Storage reduction: "
            f"{reduction:.2f}%"
        )

    lines.append("")

    lines.append(
        "## Phase 1 Status"
    )

    lines.append("")

    if (
        raw_rows == silver_rows
        and unique_transaction_ids == silver_rows
        and null_timestamps == 0
    ):

        lines.append(
            "**PASS - Silver dataset is ready "
            "for Phase 2 feature engineering.**"
        )

    else:

        lines.append(
            "**REVIEW REQUIRED before Phase 2.**"
        )

    # ==================================================
    # Write report
    # ==================================================

    REPORT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    print("\nReport created:")

    print(
        REPORT_PATH
    )

    print("\n" + "=" * 70)
    print("PHASE 1 REPORT COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()