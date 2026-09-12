from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from explainability.explanation_bundle import (
    Phase11ExplanationBundleService,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)


class Phase11CaseExplanationService:
    """
    Read-only case -> focal transaction explanation adapter.

    It never writes to the case queue or certified Phase 10 artifacts.
    """

    def __init__(self) -> None:
        self.bundle = Phase11ExplanationBundleService()

    @staticmethod
    def _queue_columns() -> tuple[str, str]:
        if not CASE_QUEUE_PATH.exists():
            raise FileNotFoundError(CASE_QUEUE_PATH)

        schema = pl.read_parquet_schema(CASE_QUEUE_PATH)
        names = set(schema.names())

        case_column = next(
            (
                name
                for name in (
                    "case_id",
                    "investigation_id",
                    "alert_id",
                )
                if name in names
            ),
            None,
        )

        transaction_column = next(
            (
                name
                for name in (
                    "transaction_id",
                    "focal_transaction_id",
                )
                if name in names
            ),
            None,
        )

        if case_column is None:
            raise RuntimeError(
                "Case queue has no supported case identifier column."
            )

        if transaction_column is None:
            raise RuntimeError(
                "Case queue has no supported transaction identifier column."
            )

        return case_column, transaction_column

    def resolve_case(
        self,
        case_id: str,
    ) -> dict[str, Any]:
        case_column, transaction_column = self._queue_columns()

        row = (
            pl.scan_parquet(CASE_QUEUE_PATH)
            .filter(
                pl.col(case_column).cast(pl.String)
                == str(case_id)
            )
            .select(
                [
                    pl.col(case_column)
                    .cast(pl.String)
                    .alias("case_id"),
                    pl.col(transaction_column)
                    .cast(pl.String)
                    .alias("transaction_id"),
                ]
            )
            .head(1)
            .collect()
        )

        if row.height == 0:
            raise KeyError(
                f"Unknown case_id: {case_id}"
            )

        return row.to_dicts()[0]

    def explain_case(
        self,
        case_id: str,
        top_k: int = 8,
    ) -> dict[str, Any]:
        mapping = self.resolve_case(case_id)

        explanation = self.bundle.build(
            transaction_id=mapping["transaction_id"],
            top_k=top_k,
        )

        return {
            "schema_version": "phase11_case_explanation_v1",
            "case_id": mapping["case_id"],
            "transaction_id": mapping["transaction_id"],
            "explanation": explanation,
            "governance": {
                "mode": "decision_support_only",
                "human_review_required": True,
                "case_queue": "read_only",
                "certified_phase10_artifacts": "read_only",
                "ground_truth_label_exposed": False,
                "autonomous_account_blocking": False,
                "autonomous_case_closure": False,
                "autonomous_regulatory_filing": False,
            },
        }
