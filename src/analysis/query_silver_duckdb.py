from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SILVER_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)


def main():

    print("=" * 75)
    print("GraphShield AML - DuckDB Silver Analytics")
    print("=" * 75)

    if not SILVER_PATH.exists():
        print("\nERROR: Silver dataset not found.")
        print(SILVER_PATH)
        return

    print("\nSilver dataset:")
    print(SILVER_PATH)

    # DuckDB works well with forward-slash paths,
    # including on Windows.
    parquet_path = SILVER_PATH.as_posix()

    con = duckdb.connect()

    # ==================================================
    # 1. Total transactions
    # ==================================================

    print("\n--- 1. DATASET SIZE ---")

    query = f"""
    SELECT
        COUNT(*) AS total_transactions
    FROM read_parquet('{parquet_path}');
    """

    result = con.execute(query).pl()

    print(result)

    # ==================================================
    # 2. Label distribution
    # ==================================================

    print("\n--- 2. LABEL DISTRIBUTION ---")

    query = f"""
    SELECT
        is_laundering,
        COUNT(*) AS transactions,
        ROUND(
            COUNT(*) * 100.0
            / SUM(COUNT(*)) OVER (),
            6
        ) AS percentage
    FROM read_parquet('{parquet_path}')
    GROUP BY is_laundering
    ORDER BY is_laundering;
    """

    result = con.execute(query).pl()

    print(result)

    # ==================================================
    # 3. Transaction time range
    # ==================================================

    print("\n--- 3. TRANSACTION TIME RANGE ---")

    query = f"""
    SELECT
        MIN(event_ts) AS earliest_transaction,
        MAX(event_ts) AS latest_transaction,
        COUNT(DISTINCT CAST(event_ts AS DATE))
            AS unique_days
    FROM read_parquet('{parquet_path}');
    """

    print(
        con.execute(query).pl()
    )

    # ==================================================
    # 4. Payment-format analysis
    # ==================================================

    print("\n--- 4. PAYMENT FORMAT SUMMARY ---")

    query = f"""
    SELECT
        payment_format,
        COUNT(*) AS transactions,
        SUM(is_laundering) AS laundering_transactions,

        ROUND(
            SUM(is_laundering) * 100.0
            / COUNT(*),
            6
        ) AS laundering_rate_percent

    FROM read_parquet('{parquet_path}')

    GROUP BY payment_format

    ORDER BY transactions DESC;
    """

    print(
        con.execute(query).pl()
    )

    # ==================================================
    # 5. Cross-bank activity
    # ==================================================

    print("\n--- 5. SAME BANK VS CROSS BANK ---")

    query = f"""
    SELECT

        from_bank != to_bank AS is_cross_bank,

        COUNT(*) AS transactions,

        SUM(is_laundering)
            AS laundering_transactions,

        ROUND(
            SUM(is_laundering) * 100.0
            / COUNT(*),
            6
        ) AS laundering_rate_percent

    FROM read_parquet('{parquet_path}')

    GROUP BY is_cross_bank

    ORDER BY is_cross_bank;
    """

    print(
        con.execute(query).pl()
    )

    # ==================================================
    # 6. Most active sender accounts
    # ==================================================

    print("\n--- 6. TOP 20 ACTIVE SENDERS ---")

    query = f"""
    SELECT

        from_account,

        COUNT(*) AS transactions_sent,

        COUNT(DISTINCT to_account)
            AS unique_receivers,

        SUM(amount_paid)
            AS total_amount_sent,

        AVG(amount_paid)
            AS average_amount_sent

    FROM read_parquet('{parquet_path}')

    GROUP BY from_account

    ORDER BY transactions_sent DESC

    LIMIT 20;
    """

    print(
        con.execute(query).pl()
    )

    # ==================================================
    # 7. Largest transactions
    # ==================================================

    print("\n--- 7. TOP 10 TRANSACTIONS BY AMOUNT ---")

    query = f"""
    SELECT

        transaction_id,
        event_ts,
        from_account,
        to_account,
        amount_paid,
        payment_currency,
        payment_format,
        is_laundering

    FROM read_parquet('{parquet_path}')

    ORDER BY amount_paid DESC

    LIMIT 10;
    """

    print(
        con.execute(query).pl()
    )

    con.close()

    print("\n" + "=" * 75)
    print("DUCKDB ANALYSIS COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()