from pathlib import Path

import polars as pl
import torch


from tgn_common import (
    NODE_PATH,
    PROJECT_ROOT,
    build_system,
    load_event_bundle,
    load_parameter_state,
    replay_split,
    reset_system,
)


CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "models"
    / "tgn_risk_v1.pt"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
    / "tgn_node_memory_validation_cutoff.parquet"
)


CHUNK_SIZE = 100_000


def main():

    print("=" * 90)
    print("GraphShield AML - Export TGN Node Memory")
    print("=" * 90)

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    checkpoint = torch.load(
        CHECKPOINT_PATH,
        map_location=device,
    )

    config = checkpoint[
        "config"
    ]

    bundle = load_event_bundle(
        max_train_events=(
            config[
                "max_train_events"
            ]
        ),

        max_val_events=(
            config[
                "max_val_events"
            ]
        ),

        max_test_events=(
            config[
                "max_test_events"
            ]
        ),
    )

    system = build_system(
        bundle,
        device,

        memory_dim=(
            config[
                "memory_dim"
            ]
        ),

        time_dim=(
            config[
                "time_dim"
            ]
        ),

        embedding_dim=(
            config[
                "embedding_dim"
            ]
        ),

        neighbor_size=(
            config[
                "neighbor_size"
            ]
        ),
    )

    load_parameter_state(
        system.memory,
        checkpoint[
            "memory_parameters"
        ],
    )

    system.gnn.load_state_dict(
        checkpoint[
            "gnn_state"
        ]
    )

    system.classifier.load_state_dict(
        checkpoint[
            "classifier_state"
        ]
    )

    reset_system(
        system
    )

    system.memory.eval()

    print(
        "\nReplaying train history..."
    )

    replay_split(
        bundle,
        system,
        device,
        "train",
    )

    print(
        "Replaying validation history..."
    )

    replay_split(
        bundle,
        system,
        device,
        "validation",
    )

    memory_dim = (
        config[
            "memory_dim"
        ]
    )

    frames = []

    print(
        "\nExtracting node memories..."
    )

    with torch.no_grad():

        for start in range(
            0,
            bundle.num_nodes,
            CHUNK_SIZE,
        ):

            end = min(
                start + CHUNK_SIZE,
                bundle.num_nodes,
            )

            node_ids = torch.arange(
                start,
                end,
                dtype=torch.long,
                device=device,
            )

            memory_values, last_update = (
                system.memory(
                    node_ids
                )
            )

            memory_values = (
                memory_values
                .cpu()
                .numpy()
            )

            last_update = (
                last_update
                .cpu()
                .numpy()
            )

            data = {
                "node_id":
                    range(
                        start,
                        end,
                    ),

                "last_update_seconds":
                    last_update,
            }

            for dimension in range(
                memory_dim
            ):

                data[
                    f"tgn_memory_{dimension:02d}"
                ] = (
                    memory_values[
                        :,
                        dimension
                    ]
                )

            frames.append(
                pl.DataFrame(
                    data
                )
            )

            print(
                f"  {end:,}/"
                f"{bundle.num_nodes:,}"
            )

    embeddings = pl.concat(
        frames,
        how="vertical",
    )

    node_mapping = (
        pl.read_parquet(
            NODE_PATH
        )
    )

    embeddings = (
        node_mapping
        .join(
            embeddings,
            on="node_id",
            how="left",
        )
    )

    embeddings.write_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()