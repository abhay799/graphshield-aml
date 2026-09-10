from pathlib import Path

import json

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CASE_QUEUE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_queue.parquet"
)

MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "subgraph_manifest.parquet"
)

PATHS_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_paths.jsonl"
)

RULE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "transaction_features_v6_rules.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "bundles"
)

INDEX_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "cases"
    / "case_bundle_index.jsonl"
)




def load_paths():

    result = {}

    if not PATHS_PATH.exists():
        return result

    with open(
        PATHS_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        for line in file:

            item = json.loads(
                line
            )

            result[
                item[
                    "case_id"
                ]
            ] = item

    return result


def main():

    print("=" * 90)
    print("GraphShield AML - Investigator Case Bundles")
    print("=" * 90)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    cases = (
        pl.read_parquet(
            CASE_QUEUE_PATH
        )
        .sort("risk_rank")
        .head(374)
    )

    case_ids = cases[
        "transaction_id"
    ].to_list()

    manifests = (
        pl.read_parquet(
            MANIFEST_PATH
        )
    )

    manifest_map = {
        row["case_id"]: row
        for row in manifests.iter_rows(
            named=True
        )
    }

    paths = load_paths()

    rules = (
        pl.scan_parquet(
            RULE_PATH
        )
        .filter(
            pl.col(
                "transaction_id"
            )
            .is_in(case_ids)
        )
        .select(
            [
                "transaction_id",

                "rule_high_velocity",
                "rule_rapid_fan_out",
                "rule_rapid_fan_in",
                "rule_rapid_pass_through",

                "rule_hit_count",
                "any_rule_hit",
            ]
        )
        .collect()
    )

    rule_map = {
        row["transaction_id"]: row
        for row in rules.iter_rows(
            named=True
        )
    }

    with open(
        INDEX_PATH,
        "w",
        encoding="utf-8",
    ) as index_file:

        for case in cases.iter_rows(
            named=True
        ):

            case_id = case[
                "case_id"
            ]

            tx_id = case[
                "transaction_id"
            ]

            rule_info = rule_map.get(
                tx_id,
                {}
            )

            manifest = (
                manifest_map.get(
                    case_id,
                    {}
                )
            )

            path_info = (
                paths.get(
                    case_id,
                    {}
                )
            )

            bundle = {
                "case_metadata": {
                    "case_id":
                        case_id,

                    "status":
                        case[
                            "case_status"
                        ],

                    "risk_rank":
                        case[
                            "risk_rank"
                        ],

                    "risk_percentile":
                        case[
                            "risk_percentile"
                        ],

                    "source_model":
                        case[
                            "source_model"
                        ],
                },

                "focal_transaction": {
                    "transaction_id":
                        tx_id,

                    "event_ts":
                        str(
                            case[
                                "event_ts"
                            ]
                        ),

                    "from_entity_id":
                        case[
                            "from_entity_id"
                        ],

                    "to_entity_id":
                        case[
                            "to_entity_id"
                        ],

                    "from_account_key":
                        case[
                            "from_account_key"
                        ],

                    "to_account_key":
                        case[
                            "to_account_key"
                        ],

                    "amount_paid":
                        case[
                            "amount_paid"
                        ],

                    "currency":
                        case[
                            "payment_currency"
                        ],

                    "payment_format":
                        case[
                            "payment_format"
                        ],
                },

                "risk": {
                    "score":
                        case[
                            "risk_score"
                        ],

                    "review_capacity":
                        case[
                            "review_capacity"
                        ],
                },

                "rule_evidence": {
                    "high_velocity":
                        rule_info.get(
                            "rule_high_velocity",
                            0,
                        ),

                    "rapid_fan_out":
                        rule_info.get(
                            "rule_rapid_fan_out",
                            0,
                        ),

                    "rapid_fan_in":
                        rule_info.get(
                            "rule_rapid_fan_in",
                            0,
                        ),

                    "rapid_pass_through":
                        rule_info.get(
                            "rule_rapid_pass_through",
                            0,
                        ),

                    "rule_hit_count":
                        rule_info.get(
                            "rule_hit_count",
                            0,
                        ),
                },

                "graph_evidence": {
                    "node_count":
                        manifest.get(
                            "node_count"
                        ),

                    "edge_count":
                        manifest.get(
                            "edge_count"
                        ),

                    "alternate_forward_path":
                        path_info.get(
                            "alternate_forward_path"
                        ),

                    "reverse_prior_path":
                        path_info.get(
                            "reverse_prior_path"
                        ),

                    "has_alternate_forward_path":
                        path_info.get(
                            "has_alternate_forward_path",
                            False,
                        ),

                    "closes_multi_hop_cycle":
                        path_info.get(
                            "closes_multi_hop_cycle",
                            False,
                        ),
                },

                "entity_resolution": {
                    "policy":
                        "exact bank-account identity only",

                    "cross_account_merging":
                        False,

                    "reason":
                        (
                            "Synthetic source lacks sufficient "
                            "KYC/PII evidence for reliable "
                            "cross-account identity resolution."
                        ),
                },

                "investigation_policy": {
                    "decision":
                        "analyst_review_required",

                    "autonomous_account_block":
                        False,

                    "autonomous_case_closure":
                        False,

                    "ground_truth_exposed":
                        False,
                },
            }

            output_path = (
                OUTPUT_DIR
                / f"{case_id}.json"
            )

            output_path.write_text(
                json.dumps(
                    bundle,
                    indent=2,
                ),
                encoding="utf-8",
            )

            index_file.write(
                json.dumps(
                    {
                        "case_id":
                            case_id,

                        "transaction_id":
                            tx_id,

                        "bundle_path":
                            str(
                                output_path
                            ),
                    }
                )
                + "\n"
            )

    print("\nCreated:")
    print(OUTPUT_DIR)
    print(INDEX_PATH)


if __name__ == "__main__":
    main()