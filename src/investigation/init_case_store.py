from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)

DB_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_store.duckdb"
)


def sql_path(path: Path) -> str:
    return (
        str(path.resolve())
        .replace("\\", "/")
        .replace("'", "''")
    )


def main():

    print("=" * 90)
    print("GraphShield AML - Initialize Case Store")
    print("=" * 90)

    if not CASE_QUEUE_PATH.exists():
        print("\nERROR: case_queue.parquet missing.")
        return

    con = duckdb.connect(
        str(DB_PATH)
    )

    case_path = sql_path(
        CASE_QUEUE_PATH
    )

    # ======================================================
    # Cases
    # ======================================================

    con.execute(
        f"""
        CREATE OR REPLACE TABLE cases AS

        SELECT
            case_id,
            transaction_id,
            event_ts,

            risk_rank,
            risk_score,
            risk_percentile,

            source_model,

            from_entity_id,
            to_entity_id,

            from_account_key,
            to_account_key,

            amount_paid,
            payment_currency,
            payment_format,

            case_status,
            review_capacity

        FROM read_parquet(
            '{case_path}'
        )
        """
    )

    # ======================================================
    # Evidence documents
    # ======================================================

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_documents (
            evidence_id VARCHAR PRIMARY KEY,
            case_id VARCHAR,
            source_type VARCHAR,
            source_ref VARCHAR,
            evidence_ts VARCHAR,
            content VARCHAR,
            point_in_time_safe BOOLEAN
        )
        """
    )

    # ======================================================
    # Analyst notes
    # ======================================================

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS case_notes (
            note_id VARCHAR PRIMARY KEY,
            case_id VARCHAR,
            created_at TIMESTAMP,
            author VARCHAR,
            note_text VARCHAR
        )
        """
    )

    # ======================================================
    # Audit log
    # ======================================================

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id VARCHAR PRIMARY KEY,
            case_id VARCHAR,
            created_at TIMESTAMP,
            actor VARCHAR,
            action VARCHAR,
            details_json VARCHAR
        )
        """
    )

    # ======================================================
    # Indexes
    # ======================================================

    con.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_cases_case_id
        ON cases(case_id)
        """
    )

    con.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_cases_transaction
        ON cases(transaction_id)
        """
    )

    con.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_evidence_case
        ON evidence_documents(case_id)
        """
    )

    case_count = (
        con.execute(
            """
            SELECT COUNT(*)
            FROM cases
            """
        )
        .fetchone()[0]
    )

    print(
        f"\nCases loaded: "
        f"{case_count:,}"
    )

    print("\nTables:")

    print(
        con.execute(
            "SHOW TABLES"
        ).fetchdf()
    )

    con.close()

    print("\nCreated:")
    print(DB_PATH)


if __name__ == "__main__":
    main()