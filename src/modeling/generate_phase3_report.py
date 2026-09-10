from pathlib import Path

import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]

REPORT_DIR = (
    PROJECT_ROOT
    / "reports"
    / "modeling"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "phase3_modeling_report.md"
)


def load_json(filename):

    path = (
        REPORT_DIR
        / filename
    )

    if not path.exists():
        return None

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def main():

    champion_selection = load_json(
        "final_champion_selection.json"
    )

    champion_test = load_json(
        "champion_test_metrics.json"
    )

    comparison = load_json(
        "rules_vs_ml.json"
    )

    if champion_selection is None:

        print(
            "ERROR: Champion selection missing."
        )

        return

    champion = (
        champion_selection[
            "champion"
        ]
    )

    lines = []

    lines.append(
        "# GraphShield AML — Phase 3 Modeling Report"
    )

    lines.append("")

    lines.append(
        "## Modeling Objective"
    )

    lines.append("")

    lines.append(
        "Prioritize transactions for analyst review "
        "using point-in-time AML risk features."
    )

    lines.append("")

    lines.append(
        "The system is an investigation prioritization "
        "prototype using public/synthetic data and is "
        "not a production AML compliance decision system."
    )

    lines.append("")

    lines.append(
        "## Final Model Selection"
    )

    lines.append("")

    lines.append(
        f"Champion: **{champion}**"
    )

    lines.append("")

    lines.append(
        "Selection was performed using validation data."
    )

    lines.append("")

    lines.append(
        "Primary metric: Average Precision."
    )

    lines.append("")

    lines.append(
        "Secondary metric: Recall@Top1%."
    )

    lines.append("")

    lines.append(
        "## Validation Candidates"
    )

    lines.append("")

    lines.append(
        "| Model | AP | Recall@1% | Recall@5% | Precision@1% |"
    )

    lines.append(
        "|---|---:|---:|---:|---:|"
    )

    for name, metrics in (
        champion_selection[
            "candidates"
        ].items()
    ):

        lines.append(
            f"| {name} "
            f"| {metrics['average_precision']:.6f} "
            f"| {metrics['recall_at_top_1pct']:.4f} "
            f"| {metrics['recall_at_top_5pct']:.4f} "
            f"| {metrics['precision_at_top_1pct']:.6f} |"
        )

    if champion_test:

        calibrated = (
            champion_test[
                "calibrated"
            ]
        )

        lines.append("")

        lines.append(
            "## Final Test Performance"
        )

        lines.append("")

        lines.append(
            f"- Average Precision: "
            f"{calibrated['average_precision']:.6f}"
        )

        lines.append(
            f"- ROC-AUC: "
            f"{calibrated['roc_auc']:.6f}"
        )

        lines.append(
            f"- Recall@Top1%: "
            f"{calibrated['recall_at_top_1pct']:.4f}"
        )

        lines.append(
            f"- Recall@Top5%: "
            f"{calibrated['recall_at_top_5pct']:.4f}"
        )

        lines.append(
            f"- Recall@Top10%: "
            f"{calibrated['recall_at_top_10pct']:.4f}"
        )

        lines.append(
            f"- Brier Score: "
            f"{calibrated['brier_score']:.8f}"
        )

        lines.append(
            f"- ECE: "
            f"{calibrated['ece_10_bins']:.8f}"
        )

    if comparison:

        lines.append("")

        lines.append(
            "## Rules vs ML"
        )

        lines.append("")

        lines.append(
            "| Capacity | Rule Recall | ML Recall | Rule Precision | ML Precision |"
        )

        lines.append(
            "|---|---:|---:|---:|---:|"
        )

        for key in [
            "top_1pct",
            "top_5pct",
            "top_10pct",
        ]:

            rule = (
                comparison[
                    "rules"
                ][key]
            )

            ml = (
                comparison[
                    "ml"
                ][key]
            )

            lines.append(
                f"| {key} "
                f"| {rule['recall']:.4f} "
                f"| {ml['recall']:.4f} "
                f"| {rule['precision']:.6f} "
                f"| {ml['precision']:.6f} |"
            )

    lines.append("")

    lines.append(
        "## Explainability"
    )

    lines.append("")

    lines.append(
        "TreeSHAP explanations are generated for "
        "global feature importance and high-risk "
        "transaction-level explanations."
    )

    lines.append("")

    lines.append(
        "## Next Phase"
    )

    lines.append("")

    lines.append(
        "Phase 4 will introduce graph-native account "
        "and transaction features to capture relationships "
        "that transaction-level tabular models may miss."
    )

    OUTPUT_PATH.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(
        "\nCreated:"
    )

    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()