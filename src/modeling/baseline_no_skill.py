import numpy as np
import polars as pl

from common import (
    DATA_PATH,
    REPORT_DIR,
    TARGET,
    ensure_directories,
)

from metrics import (
    evaluate_binary,
    save_json,
)


def get_labels(split_name):

    return (
        pl.scan_parquet(DATA_PATH)
        .filter(
            pl.col("split")
            == split_name
        )
        .select(TARGET)
        .collect()[TARGET]
        .to_numpy()
        .astype("int8")
    )


def main():

    ensure_directories()

    print("=" * 80)
    print("GraphShield AML - Phase 3.2 Baselines")
    print("=" * 80)

    train_prevalence = (
        pl.scan_parquet(DATA_PATH)
        .filter(
            pl.col("split") == "train"
        )
        .select(
            pl.col(TARGET).mean()
        )
        .collect()
        .item()
    )

    print(
        f"\nTraining prevalence: "
        f"{train_prevalence:.8f}"
    )

    results = {}

    rng = np.random.default_rng(42)

    for split_name in [
        "validation",
        "test",
    ]:

        y = get_labels(split_name)

        # Constant probability baseline
        constant_probability = (
            np.full(
                len(y),
                train_prevalence,
                dtype=float,
            )
        )

        constant_metrics = (
            evaluate_binary(
                y,
                constant_probability,
            )
        )

        # Random ranking baseline
        random_scores = (
            rng.random(
                len(y)
            )
        )

        random_metrics = (
            evaluate_binary(
                y,
                random_scores,
            )
        )

        results[split_name] = {
            "constant": constant_metrics,
            "random_ranking": random_metrics,
        }

        print(
            f"\n--- {split_name.upper()} ---"
        )

        print(
            "No-skill AP:",
            constant_metrics[
                "average_precision"
            ],
        )

        print(
            "Random Recall@Top1%:",
            random_metrics[
                "recall_at_top_1pct"
            ],
        )

    save_json(
        REPORT_DIR
        / "baseline_metrics.json",
        results,
    )

    print(
        "\nSaved baseline metrics."
    )


if __name__ == "__main__":
    main()