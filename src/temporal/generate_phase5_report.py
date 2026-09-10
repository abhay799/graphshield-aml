from pathlib import Path

import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "graph_ablation_metrics.json"
)

TGN_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "tgn_metrics.json"
)

HYBRID_REPORT = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
    / "tgn_hybrid_fusion.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "phase5_temporal_graph_report.md"
)


def load_json(
    path,
):

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def table_row(
    name,
    metrics,
):

    return (
        f"| {name} "
        f"| {metrics['average_precision']:.6f} "
        f"| {metrics['recall_at_top_1pct']:.4f} "
        f"| {metrics['recall_at_top_5pct']:.4f} "
        f"| {metrics['precision_at_top_1pct']:.6f} |"
    )


def main():

    graph = load_json(
        GRAPH_REPORT
    )

    tgn = load_json(
        TGN_REPORT
    )

    hybrid = load_json(
        HYBRID_REPORT
    )

    validation_models = {
        "Transaction LightGBM":
            graph[
                "baseline_validation"
            ],

        "Transaction + Graph LightGBM":
            graph[
                "graph_validation"
            ],

        "TGN":
            tgn[
                "final_validation"
            ],

        "Graph + TGN Hybrid":
            hybrid[
                "validation_hybrid"
            ],
    }

    test_models = {
        "Transaction LightGBM":
            graph[
                "baseline_test"
            ],

        "Transaction + Graph LightGBM":
            graph[
                "graph_test"
            ],

        "TGN":
            tgn[
                "final_test"
            ],

        "Graph + TGN Hybrid":
            hybrid[
                "test_hybrid"
            ],
    }

    champion = max(
        validation_models,
        key=lambda name: (
            validation_models[
                name
            ][
                "average_precision"
            ],

            validation_models[
                name
            ][
                "recall_at_top_1pct"
            ],
        ),
    )

    lines = [
        "# GraphShield AML — Phase 5 Temporal Graph Learning",
        "",
        "## Objective",
        "",
        (
            "Measure whether learned temporal graph state "
            "adds value beyond transaction-level and "
            "handcrafted point-in-time graph features."
        ),
        "",
        "## Validation Comparison",
        "",
        (
            "| Model | Average Precision | "
            "Recall@1% | Recall@5% | Precision@1% |"
        ),
        "|---|---:|---:|---:|---:|",
    ]

    for name, metrics in (
        validation_models.items()
    ):

        lines.append(
            table_row(
                name,
                metrics,
            )
        )

    lines.extend(
        [
            "",
            "## Test Comparison",
            "",
            (
                "| Model | Average Precision | "
                "Recall@1% | Recall@5% | Precision@1% |"
            ),
            "|---|---:|---:|---:|---:|",
        ]
    )

    for name, metrics in (
        test_models.items()
    ):

        lines.append(
            table_row(
                name,
                metrics,
            )
        )

    lines.extend(
        [
            "",
            "## Validation-Selected Champion",
            "",
            f"**{champion}**",
            "",
            (
                "The champion is selected using validation "
                "Average Precision, with Recall@Top1% as "
                "the secondary criterion."
            ),
            "",
            "## TGN Leakage Policy",
            "",
            (
                "All transactions sharing the same timestamp "
                "are scored from the same pre-timestamp graph "
                "state. The group enters TGN memory only after "
                "all predictions for that timestamp are made."
            ),
            "",
            "## Hybrid",
            "",
            (
                "The hybrid combines handcrafted graph-model "
                "and TGN rankings using a fusion weight chosen "
                "only on validation data."
            ),
            "",
            "## Interpretation",
            "",
            (
                "If TGN or the hybrid does not beat the "
                "handcrafted graph model, that is still a valid "
                "result: the engineered graph signals may already "
                "capture most of the useful temporal structure in "
                "this synthetic dataset."
            ),
        ]
    )

    OUTPUT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print("=" * 90)
    print("GraphShield AML - Phase 5 Report")
    print("=" * 90)

    print(
        "\nValidation-selected champion:"
    )

    print(champion)

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()