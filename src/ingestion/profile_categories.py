from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "raw" / "LI-Small_Trans.csv"


def main():

    print("=" * 60)
    print("GraphShield AML - Categorical Profiling")
    print("=" * 60)

    print("\nLoading dataset...")

    df = pl.read_csv(DATA_PATH)

    # --------------------------------------------------
    # Cardinality
    # --------------------------------------------------

    print("\n--- UNIQUE VALUE COUNTS ---")

    columns = [
        "From Bank",
        "Account",
        "To Bank",
        "Account_duplicated_0",
        "Receiving Currency",
        "Payment Currency",
        "Payment Format",
    ]

    for column in columns:

        unique_count = df[column].n_unique()

        print(
            f"{column:<25}: "
            f"{unique_count:,}"
        )

    # --------------------------------------------------
    # Payment formats
    # --------------------------------------------------

    print("\n--- PAYMENT FORMAT DISTRIBUTION ---")

    payment_formats = (
        df.group_by("Payment Format")
        .len()
        .sort("len", descending=True)
    )

    print(payment_formats)

    # --------------------------------------------------
    # Receiving currencies
    # --------------------------------------------------

    print("\n--- RECEIVING CURRENCY DISTRIBUTION ---")

    receiving_currency = (
        df.group_by("Receiving Currency")
        .len()
        .sort("len", descending=True)
    )

    print(receiving_currency)

    # --------------------------------------------------
    # Payment currencies
    # --------------------------------------------------

    print("\n--- PAYMENT CURRENCY DISTRIBUTION ---")

    payment_currency = (
        df.group_by("Payment Currency")
        .len()
        .sort("len", descending=True)
    )

    print(payment_currency)

    print("\n--- Done ---")


if __name__ == "__main__":
    main()