import json

import numpy as np

from sklearn.metrics import (
    auc,
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def expected_calibration_error(
    y_true,
    probabilities,
    bins=10,
):

    y_true = np.asarray(y_true)
    probabilities = np.asarray(probabilities)

    edges = np.linspace(
        0.0,
        1.0,
        bins + 1,
    )

    ece = 0.0

    for i in range(bins):

        lower = edges[i]
        upper = edges[i + 1]

        if i == bins - 1:
            mask = (
                (probabilities >= lower)
                & (probabilities <= upper)
            )
        else:
            mask = (
                (probabilities >= lower)
                & (probabilities < upper)
            )

        count = mask.sum()

        if count == 0:
            continue

        observed_rate = (
            y_true[mask].mean()
        )

        predicted_rate = (
            probabilities[mask].mean()
        )

        ece += (
            count / len(y_true)
        ) * abs(
            observed_rate
            - predicted_rate
        )

    return float(ece)


def evaluate_binary(
    y_true,
    probabilities,
    threshold=0.5,
):

    y_true = np.asarray(y_true)
    probabilities = np.asarray(
        probabilities,
        dtype=float,
    )

    probabilities = np.clip(
        probabilities,
        1e-9,
        1 - 1e-9,
    )

    predictions = (
        probabilities >= threshold
    ).astype(int)

    precision_curve, recall_curve, _ = (
        precision_recall_curve(
            y_true,
            probabilities,
        )
    )

    results = {
        "rows": int(len(y_true)),

        "positives": int(
            y_true.sum()
        ),

        "prevalence": float(
            y_true.mean()
        ),

        "roc_auc": float(
            roc_auc_score(
                y_true,
                probabilities,
            )
        ),

        "average_precision": float(
            average_precision_score(
                y_true,
                probabilities,
            )
        ),

        "pr_auc": float(
            auc(
                recall_curve[::-1],
                precision_curve[::-1],
            )
        ),

        "brier_score": float(
            brier_score_loss(
                y_true,
                probabilities,
            )
        ),

        "ece_10_bins": (
            expected_calibration_error(
                y_true,
                probabilities,
                bins=10,
            )
        ),

        "precision_at_0_5": float(
            precision_score(
                y_true,
                predictions,
                zero_division=0,
            )
        ),

        "recall_at_0_5": float(
            recall_score(
                y_true,
                predictions,
                zero_division=0,
            )
        ),

        "f1_at_0_5": float(
            f1_score(
                y_true,
                predictions,
                zero_division=0,
            )
        ),
    }

    # ======================================================
    # Analyst review-capacity metrics
    # ======================================================

    ranking = np.argsort(
        probabilities
    )[::-1]

    total_positives = max(
        int(y_true.sum()),
        1,
    )

    prevalence = max(
        y_true.mean(),
        1e-12,
    )

    for fraction in [
        0.01,
        0.05,
        0.10,
    ]:

        n = max(
            1,
            int(
                np.ceil(
                    len(y_true)
                    * fraction
                )
            ),
        )

        selected = ranking[:n]

        true_positives = int(
            y_true[selected].sum()
        )

        precision_at_k = (
            true_positives / n
        )

        recall_at_k = (
            true_positives
            / total_positives
        )

        lift_at_k = (
            precision_at_k
            / prevalence
        )

        label = (
            f"{int(fraction * 100)}pct"
        )

        results[
            f"precision_at_top_{label}"
        ] = float(
            precision_at_k
        )

        results[
            f"recall_at_top_{label}"
        ] = float(
            recall_at_k
        )

        results[
            f"lift_at_top_{label}"
        ] = float(
            lift_at_k
        )

    return results


def save_json(
    path,
    content,
):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            content,
            file,
            indent=2,
        )