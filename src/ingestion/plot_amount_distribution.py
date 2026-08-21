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

    print("=" * 70)
    print("GraphShield AML - Amount Distribution")
    print("=" * 70)

    print("\nLoading amount column...")

    df = pl.read_csv(
        DATA_PATH,
        columns=[
            "Amount Paid",
            "Is Laundering",
        ],
    )

    print(
        f"Transactions loaded: "
        f"{df.height:,}"
    )

    # --------------------------------------------------
    # Log transformation
    # --------------------------------------------------

    df = df.with_columns(
        pl.col("Amount Paid")
        .log1p()
        .alias("log_amount_paid")
    )

    # --------------------------------------------------
    # Plot
    # --------------------------------------------------

    values = (
        df["log_amount_paid"]
        .drop_nulls()
        .to_numpy()
    )

    plt.figure(
        figsize=(10, 6)
    )

    plt.hist(
        values,
        bins=100
    )

    plt.xlabel(
        "log(1 + Amount Paid)"
    )

    plt.ylabel(
        "Number of Transactions"
    )

    plt.title(
        "Distribution of Transaction Amounts - Log Scale"
    )

    plt.tight_layout()

    output_path = (
        FIGURE_DIR
        / "amount_paid_log_distribution.png"
    )

    plt.savefig(
        output_path,
        dpi=150
    )

    print("\nPlot saved to:")
    print(output_path)

    plt.show()


if __name__ == "__main__":
    main()