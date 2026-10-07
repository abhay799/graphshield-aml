from __future__ import annotations

import math

import polars as pl

from scripts.live_scoring.historical_pit_replay import (
    GOLD_PATH,
    _load_model_bundle,
    _score_feature_vector,
    load_targets,
    select_replay_history,
)


def test_historical_pit_scope_is_strictly_before_certified_ibm_target():
    target = load_targets(["IBM_LI_SMALL_4884658"])[0]
    history = select_replay_history(target)

    assert len(history) == 3727
    assert history
    assert all(row["event_ts"] < target["event_ts"] for row in history)

    ordering = [
        (
            row["event_ts"],
            row["source_row_number"],
            row["transaction_id"],
        )
        for row in history
    ]
    assert ordering == sorted(ordering)


def test_historical_direct_model_scoring_matches_certified_ibm_gold_vector():
    model, bundle, feature_names, categorical = _load_model_bundle()
    gold = (
        pl.scan_parquet(GOLD_PATH)
        .filter(pl.col("transaction_id") == "IBM_LI_SMALL_4884658")
        .select(feature_names)
        .collect(engine="streaming")
        .to_dicts()[0]
    )

    raw_score, calibrated_score = _score_feature_vector(
        gold,
        model,
        bundle,
        feature_names,
        categorical,
    )

    assert math.isclose(
        raw_score,
        0.9999999999996636,
        rel_tol=0.0,
        abs_tol=1e-15,
    )
    assert math.isclose(
        calibrated_score,
        0.02738545245606547,
        rel_tol=0.0,
        abs_tol=1e-15,
    )
