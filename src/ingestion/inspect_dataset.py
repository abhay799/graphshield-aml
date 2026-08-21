import polars as pl

FILE_PATH = "data/raw/LI-Small_Trans.csv"


def main():
    print("Loading AML dataset...")

    df = pl.read_csv(
        FILE_PATH,
        n_rows=5
    )

    print("\nDataset loaded successfully!")
    print("\nColumns:")
    print(df.columns)

    print("\nFirst 5 rows:")
    print(df)


if __name__ == "__main__":
    main()