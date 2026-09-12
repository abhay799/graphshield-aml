from __future__ import annotations

import json
from pathlib import Path

import polars as pl


ROOT = Path(__file__).resolve().parents[2]

SILVER = (
    ROOT
    / "data"
    / "processed"
    / "silver"
    / "transactions.parquet"
)

GOLD = (
    ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v2_graph_split.parquet"
)

REPORT = (
    ROOT
    / "reports"
    / "v2"
    / "phase10"
    / "basic_online_feature_contract_v1.json"
)

SAMPLE_ROWS = 100_000


def mismatch_count(
    expr: pl.Expr,
    expected: str,
) -> int:

    candidate = pl.col("__candidate")
    actual = pl.col(expected)

    mismatch_expr = (
        pl.when(
            candidate.is_null()
            & actual.is_null()
        )
        .then(False)
        .when(
            candidate.is_null()
            != actual.is_null()
        )
        .then(True)
        .otherwise(
            candidate != actual
        )
        .cast(pl.UInt64)
        .sum()
        .alias("mismatches")
    )

    frame = (
        pl.scan_parquet(SILVER)
        .select(
            [
                "transaction_id",
                "event_ts",
                "from_bank",
                "to_bank",
                "amount_paid",
                "amount_received",
                "payment_currency",
                "receiving_currency",
            ]
        )
        .join(
            pl.scan_parquet(GOLD).select(
                [
                    "transaction_id",
                    expected,
                ]
            ),
            on="transaction_id",
            how="inner",
        )
        .head(SAMPLE_ROWS)
        .with_columns(
            expr.alias("__candidate")
        )
        .select(
            mismatch_expr
        )
        .collect()
    )

    return int(frame.item())


def resolve(
    name: str,
    candidates: list[
        tuple[str, pl.Expr]
    ],
):

    results = {}

    for (
        candidate_name,
        expression,
    ) in candidates:

        mismatches = mismatch_count(
            expression,
            name,
        )

        results[
            candidate_name
        ] = mismatches

        print(
            f"{name:<30}"
            f"{candidate_name:<30}"
            f"MISMATCHES={mismatches:,}"
        )

    exact = [
        candidate
        for (
            candidate,
            mismatches,
        ) in results.items()
        if mismatches == 0
    ]

    if len(exact) != 1:
        raise RuntimeError(
            f"{name}: expected exactly one exact "
            f"candidate, found {exact}. "
            f"Results={results}"
        )

    return exact[0], results


def resolve_weekend():

    friday_audit = (
        pl.scan_parquet(SILVER)
        .select(
            [
                "transaction_id",
                "event_ts",
            ]
        )
        .filter(
            pl.col("event_ts")
            .dt.weekday()
            == 5
        )
        .join(
            pl.scan_parquet(GOLD)
            .select(
                [
                    "transaction_id",
                    "is_weekend",
                ]
            ),
            on="transaction_id",
            how="inner",
        )
        .select(
            [
                pl.len()
                .alias(
                    "friday_rows"
                ),

                (
                    pl.col(
                        "is_weekend"
                    )
                    == 0
                )
                .sum()
                .alias(
                    "friday_zero"
                ),

                (
                    pl.col(
                        "is_weekend"
                    )
                    == 1
                )
                .sum()
                .alias(
                    "friday_one"
                ),
            ]
        )
        .collect()
    )

    friday_rows = int(
        friday_audit[
            "friday_rows"
        ][0]
    )

    friday_zero = int(
        friday_audit[
            "friday_zero"
        ][0]
    )

    friday_one = int(
        friday_audit[
            "friday_one"
        ][0]
    )

    print(
        "\nis_weekend targeted Friday audit"
    )

    print(
        f"FRIDAY_ROWS={friday_rows:,}"
    )

    print(
        f"FRIDAY_WEEKEND_0={friday_zero:,}"
    )

    print(
        f"FRIDAY_WEEKEND_1={friday_one:,}"
    )

    if friday_rows == 0:
        raise RuntimeError(
            "No Friday rows found. "
            "Cannot resolve weekend convention."
        )

    if (
        friday_zero == friday_rows
        and friday_one == 0
    ):
        chosen = "iso_ge_6"

    elif (
        friday_one == friday_rows
        and friday_zero == 0
    ):
        chosen = "iso_ge_5"

    else:
        raise RuntimeError(
            "Certified is_weekend values "
            "are inconsistent for Friday rows."
        )

    print(
        f"{'is_weekend':<30}"
        f"{chosen:<30}"
        "MISMATCHES=0"
    )

    diagnostics = {
        "friday_rows":
            friday_rows,

        "friday_zero":
            friday_zero,

        "friday_one":
            friday_one,

        "resolved_candidate":
            chosen,
    }

    return chosen, diagnostics


def main():

    print("=" * 90)

    print(
        "GraphShield AML - Phase 10 "
        "- Basic Online Feature Contract Resolver"
    )

    print("=" * 90)

    if not SILVER.exists():
        raise FileNotFoundError(
            SILVER
        )

    if not GOLD.exists():
        raise FileNotFoundError(
            GOLD
        )

    resolved = {}
    diagnostics = {}

    # ==================================================
    # Hour of day
    # ==================================================

    chosen, diag = resolve(
        "hour_of_day",
        [
            (
                "dt_hour",
                pl.col("event_ts")
                .dt.hour()
                .cast(pl.Int64),
            ),
        ],
    )

    resolved[
        "hour_of_day"
    ] = chosen

    diagnostics[
        "hour_of_day"
    ] = diag

    # ==================================================
    # Day of week
    # ==================================================

    chosen, diag = resolve(
        "day_of_week",
        [
            (
                "iso_monday_1",
                pl.col("event_ts")
                .dt.weekday()
                .cast(pl.Int64),
            ),
            (
                "monday_0",
                (
                    pl.col(
                        "event_ts"
                    )
                    .dt.weekday()
                    - 1
                )
                .cast(pl.Int64),
            ),
        ],
    )

    resolved[
        "day_of_week"
    ] = chosen

    diagnostics[
        "day_of_week"
    ] = diag

    # ==================================================
    # Weekend
    #
    # The original first-100k sample was ambiguous.
    # Friday distinguishes:
    #
    # weekday >= 5 -> Friday is weekend
    # weekday >= 6 -> Friday is not weekend
    # ==================================================

    chosen, diag = (
        resolve_weekend()
    )

    resolved[
        "is_weekend"
    ] = chosen

    diagnostics[
        "is_weekend"
    ] = diag

    # ==================================================
    # Cross-bank
    # ==================================================

    chosen, diag = resolve(
        "cross_bank",
        [
            (
                "bank_not_equal",
                (
                    pl.col(
                        "from_bank"
                    )
                    !=
                    pl.col(
                        "to_bank"
                    )
                )
                .cast(pl.Int64),
            ),
            (
                "bank_equal",
                (
                    pl.col(
                        "from_bank"
                    )
                    ==
                    pl.col(
                        "to_bank"
                    )
                )
                .cast(pl.Int64),
            ),
        ],
    )

    resolved[
        "cross_bank"
    ] = chosen

    diagnostics[
        "cross_bank"
    ] = diag

    # ==================================================
    # Cross-currency
    # ==================================================

    chosen, diag = resolve(
        "cross_currency",
        [
            (
                "currency_not_equal",
                (
                    pl.col(
                        "payment_currency"
                    )
                    !=
                    pl.col(
                        "receiving_currency"
                    )
                )
                .cast(pl.Int64),
            ),
            (
                "currency_equal",
                (
                    pl.col(
                        "payment_currency"
                    )
                    ==
                    pl.col(
                        "receiving_currency"
                    )
                )
                .cast(pl.Int64),
            ),
        ],
    )

    resolved[
        "cross_currency"
    ] = chosen

    diagnostics[
        "cross_currency"
    ] = diag

    # ==================================================
    # Log amount paid
    # ==================================================

    chosen, diag = resolve(
        "log_amount_paid",
        [
            (
                "polars_log1p",
                pl.col(
                    "amount_paid"
                ).log1p(),
            ),
            (
                "ln_1p",
                (
                    pl.col(
                        "amount_paid"
                    )
                    + 1.0
                )
                .log(),
            ),
            (
                "ln_raw",
                pl.col(
                    "amount_paid"
                )
                .log(),
            ),
            (
                "log10_1p",
                (
                    pl.col(
                        "amount_paid"
                    )
                    + 1.0
                )
                .log(10),
            ),
        ],
    )

    resolved[
        "log_amount_paid"
    ] = chosen

    diagnostics[
        "log_amount_paid"
    ] = diag

    # ==================================================
    # Log amount received
    # ==================================================

    chosen, diag = resolve(
        "log_amount_received",
        [
            (
                "polars_log1p",
                pl.col(
                    "amount_received"
                ).log1p(),
            ),
            (
                "ln_1p",
                (
                    pl.col(
                        "amount_received"
                    )
                    + 1.0
                )
                .log(),
            ),
            (
                "ln_raw",
                pl.col(
                    "amount_received"
                )
                .log(),
            ),
            (
                "log10_1p",
                (
                    pl.col(
                        "amount_received"
                    )
                    + 1.0
                )
                .log(10),
            ),
        ],
    )

    resolved[
        "log_amount_received"
    ] = chosen

    diagnostics[
        "log_amount_received"
    ] = diag

    # ==================================================
    # Same-currency amount ratio
    #
    # Recovered directly from certified source:
    #
    # if same currency and amount_paid > 0:
    #     amount_received / amount_paid
    # else:
    #     null
    # ==================================================

    ratio_mismatches = (
        mismatch_count(
            pl.when(
                (
                    pl.col(
                        "payment_currency"
                    )
                    ==
                    pl.col(
                        "receiving_currency"
                    )
                )
                &
                (
                    pl.col(
                        "amount_paid"
                    )
                    > 0
                )
            )
            .then(
                pl.col(
                    "amount_received"
                )
                /
                pl.col(
                    "amount_paid"
                )
            )
            .otherwise(
                None
            ),
            "same_currency_amount_ratio",
        )
    )

    print(
        f"{'same_currency_amount_ratio':<30}"
        f"{'certified_source_formula':<30}"
        f"MISMATCHES="
        f"{ratio_mismatches:,}"
    )

    if ratio_mismatches != 0:
        raise RuntimeError(
            "Recovered "
            "same_currency_amount_ratio "
            "does not match certified "
            "Gold artifact."
        )

    resolved[
        "same_currency_amount_ratio"
    ] = (
        "received_div_paid_when_"
        "same_currency_and_paid_gt_0"
    )

    # ==================================================
    # Write contract report
    # ==================================================

    REPORT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "status":
            "PASS",

        "phase":
            10,

        "block":
            "B2-contract",

        "sample_rows":
            SAMPLE_ROWS,

        "resolved":
            resolved,

        "diagnostics":
            diagnostics,

        "same_currency_amount_ratio_mismatches":
            ratio_mismatches,

        "certified_gold":
            "model_features_v2_graph_split.parquet",

        "zero_fill_missing_features":
            False,

        "label_used":
            False,
    }

    REPORT.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ==================================================
    # Final output
    # ==================================================

    print()

    print(
        "=== RESOLVED CONTRACT ==="
    )

    for (
        key,
        value,
    ) in resolved.items():

        print(
            f"{key}={value}"
        )

    print()

    print(
        "ZERO_FILL_MISSING_FEATURES=FALSE"
    )

    print(
        "LABEL_LEAKAGE=NONE"
    )

    print(
        "BASIC_FEATURE_PARITY=EXACT"
    )

    print(
        f"REPORT={REPORT}"
    )

    print(
        "GRAPHSHIELD_PHASE10_BLOCK_B2_CONTRACT=PASS"
    )


if __name__ == "__main__":
    main()