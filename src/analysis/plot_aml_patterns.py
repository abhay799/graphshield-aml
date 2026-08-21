from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "LI-Small_Trans.csv"
)

FIGURE_DIR = (
    PROJECT_ROOT
    / "reports"
    / "figures"
)

FIGURE_DIR.mkdir(
    parents=True,
    exist_ok=True
)


def main():

    lf = pl.scan_csv(DATA_PATH)

    # ==================================================
    # Laundering rate by payment format
    # ==================================================

    payment_data = (
        lf.group_by("Payment Format")
        .agg(
            [
                pl.len().alias("transactions"),

                pl.col("Is Laundering")
                .sum()
                .alias("laundering_transactions"),
            ]
        )
        .with_columns(
            (
                pl.col("laundering_transactions")
                / pl.col("transactions")
                * 100
            ).alias("laundering_rate")
        )
        .sort(
            "laundering_rate",
            descending=True
        )
        .collect()
    )

    formats = payment_data[
        "Payment Format"
    ].to_list()

    rates = payment_data[
        "laundering_rate"
    ].to_list()

    plt.figure(
        figsize=(10, 6)
    )

    plt.bar(
        formats,
        rates
    )

    plt.xlabel(
        "Payment Format"
    )

    plt.ylabel(
        "Laundering Rate (%)"
    )

    plt.title(
        "Laundering Rate by Payment Format"
    )

    plt.xticks(
        rotation=45,
        ha="right"
    )

    plt.tight_layout()

    output = (
        FIGURE_DIR
        / "laundering_rate_by_payment_format.png"
    )

    plt.savefig(
        output,
        dpi=150
    )

    print("Plot saved:")
    print(output)

    plt.show()


if __name__ == "__main__":
    main()