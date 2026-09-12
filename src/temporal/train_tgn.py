from pathlib import Path

import json
import os

import numpy as np
import polars as pl
import torch


from tgn_common import (
    PROJECT_ROOT,
    build_system,
    evaluate_scores,
    evaluate_split,
    load_event_bundle,
    load_parameter_state,
    model_parameters,
    parameter_state,
    replay_split,
    reset_system,
    score_group,
    update_group,
)


MODEL_DIR = Path(
    os.getenv(
        "GS_TGN_MODEL_DIR",
        str(PROJECT_ROOT / "models"),
    )
)

REPORT_DIR = Path(
    os.getenv(
        "GS_TGN_REPORT_DIR",
        str(PROJECT_ROOT / "reports" / "modeling"),
    )
)

PREDICTION_DIR = Path(
    os.getenv(
        "GS_TGN_PREDICTION_DIR",
        str(PROJECT_ROOT / "data" / "processed" / "modeling"),
    )
)

CHECKPOINT_PATH = Path(
    os.getenv(
        "GS_TGN_CHECKPOINT_PATH",
        str(MODEL_DIR / "tgn_risk_v1.pt"),
    )
)


def env_int(
    name,
    default,
):

    value = int(
        os.getenv(
            name,
            str(default),
        )
    )

    return (
        None
        if value <= 0
        else value
    )


MAX_TRAIN_EVENTS = env_int(
    "GS_TGN_MAX_TRAIN_EVENTS",
    0,
)

MAX_VAL_EVENTS = env_int(
    "GS_TGN_MAX_VAL_EVENTS",
    0,
)

MAX_TEST_EVENTS = env_int(
    "GS_TGN_MAX_TEST_EVENTS",
    0,
)


def env_bool(name, default=False):
    value = os.getenv(
        name,
        "1" if default else "0",
    ).strip().lower()

    return value in {
        "1",
        "true",
        "yes",
        "on",
    }


# Phase 10 model-selection runs must not touch the locked test split.
# Set GS_TGN_EVAL_TEST=1 only once, after the final temporal candidate
# has been selected using validation data.
EVAL_TEST = env_bool(
    "GS_TGN_EVAL_TEST",
    False,
)


EPOCHS = int(
    os.getenv(
        "GS_TGN_EPOCHS",
        "10",
    )
)

PATIENCE = int(
    os.getenv(
        "GS_TGN_PATIENCE",
        "3",
    )
)

LEARNING_RATE = float(
    os.getenv(
        "GS_TGN_LR",
        "0.001",
    )
)


MEMORY_DIM = 32
TIME_DIM = 16
EMBEDDING_DIM = 32
NEIGHBOR_SIZE = 10


def train_epoch(
    bundle,
    system,
    device,
    optimizer,
    criterion,
    parameters,
):

    system.memory.train()
    system.gnn.train()
    system.classifier.train()

    reset_system(
        system
    )

    total_loss = 0.0
    total_events = 0

    groups = bundle.groups[
        "train"
    ]

    for group_number, (
        start,
        end,
    ) in enumerate(
        groups,
        start=1,
    ):

        optimizer.zero_grad(
            set_to_none=True
        )

        (
            src,
            dst,
            t,
            msg,
            y,
            logits,
            _,
            _,
        ) = score_group(
            bundle,
            system,
            device,
            start,
            end,
        )

        loss = criterion(
            logits,
            y,
        )

        # Current timestamp group enters memory
        # only AFTER prediction.
        update_group(
            system,
            src,
            dst,
            t,
            msg,
        )

        loss.backward()

        torch.nn.utils.clip_grad_norm_(
            parameters,
            max_norm=1.0,
        )

        optimizer.step()

        # Truncated temporal backpropagation.
        system.memory.detach()

        events = (
            end - start
        )

        total_loss += (
            float(
                loss.detach().cpu()
            )
            * events
        )

        total_events += events

        if (
            group_number % 100 == 0
        ):

            print(
                f"    timestamp groups: "
                f"{group_number:,}"
                f"/{len(groups):,}"
            )

    return (
        total_loss
        / max(
            total_events,
            1,
        )
    )


def save_checkpoint(
    system,
    config,
):

    torch.save(
        {
            # Do not persist dynamic memory buffers.
            "memory_parameters":
                parameter_state(
                    system.memory
                ),

            "gnn_state":
                system.gnn
                .state_dict(),

            "classifier_state":
                system.classifier
                .state_dict(),

            "config":
                config,
        },
        CHECKPOINT_PATH,
    )


def load_checkpoint(
    system,
    device,
):

    checkpoint = torch.load(
        CHECKPOINT_PATH,
        map_location=device,
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

    return checkpoint


def main():

    print("=" * 90)
    print("GraphShield AML - Temporal Graph Network Training")
    print("=" * 90)

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PREDICTION_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    torch.manual_seed(42)

    np.random.seed(42)

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print("\nDevice:")
    print(device)

    bundle = load_event_bundle(
        max_train_events=(
            MAX_TRAIN_EVENTS
        ),

        max_val_events=(
            MAX_VAL_EVENTS
        ),

        max_test_events=(
            MAX_TEST_EVENTS
        ),
    )

    system = build_system(
        bundle,
        device,

        memory_dim=MEMORY_DIM,
        time_dim=TIME_DIM,
        embedding_dim=EMBEDDING_DIM,
        neighbor_size=NEIGHBOR_SIZE,
    )

    parameters = model_parameters(
        system
    )

    optimizer = torch.optim.Adam(
        parameters,
        lr=LEARNING_RATE,
    )

    train_start, train_end = (
        bundle.ranges[
            "train"
        ]
    )

    y_train = (
        bundle.y[
            train_start:
            train_end
        ]
    )

    positives = int(
        y_train.sum().item()
    )

    negatives = (
        len(y_train)
        - positives
    )

    if positives == 0:

        raise RuntimeError(
            "Training subset contains zero positive "
            "transactions. Increase the training window."
        )

    pos_weight = (
        negatives
        / positives
    )

    print(
        f"\nTrain positives: "
        f"{positives:,}"
    )

    print(
        f"Train negatives: "
        f"{negatives:,}"
    )

    print(
        f"BCE pos_weight: "
        f"{pos_weight:.2f}"
    )

    criterion = (
        torch.nn.BCEWithLogitsLoss(
            pos_weight=torch.tensor(
                pos_weight,
                dtype=torch.float32,
                device=device,
            )
        )
    )

    config = {
        "memory_dim":
            MEMORY_DIM,

        "time_dim":
            TIME_DIM,

        "embedding_dim":
            EMBEDDING_DIM,

        "neighbor_size":
            NEIGHBOR_SIZE,

        "learning_rate":
            LEARNING_RATE,

        "epochs":
            EPOCHS,

        "patience":
            PATIENCE,

        "max_train_events":
            MAX_TRAIN_EVENTS,

        "max_val_events":
            MAX_VAL_EVENTS,

        "max_test_events":
            MAX_TEST_EVENTS,

        "eval_test":
            EVAL_TEST,

        "pos_weight":
            pos_weight,
    }

    best_ap = -1.0
    epochs_without_improvement = 0

    history = []

    # ======================================================
    # Train → Validation only
    #
    # Test is NOT touched here.
    # ======================================================

    for epoch in range(
        1,
        EPOCHS + 1,
    ):

        print(
            f"\n--- EPOCH "
            f"{epoch}/{EPOCHS} ---"
        )

        train_loss = train_epoch(
            bundle,
            system,
            device,
            optimizer,
            criterion,
            parameters,
        )

        # train_epoch leaves memory at the end
        # of training history.
        #
        # Switching to eval also flushes TGN's
        # pending training messages.

        y_val, val_scores = (
            evaluate_split(
                bundle,
                system,
                device,
                "validation",
            )
        )

        val_metrics = (
            evaluate_scores(
                y_val,
                val_scores,
            )
        )

        validation_ap = (
            val_metrics[
                "average_precision"
            ]
        )

        print(
            f"Train loss: "
            f"{train_loss:.6f}"
        )

        print(
            f"Validation AP: "
            f"{validation_ap:.6f}"
        )

        print(
            "Validation Recall@1%: "
            f"{val_metrics['recall_at_top_1pct']:.4f}"
        )

        history.append(
            {
                "epoch":
                    epoch,

                "train_loss":
                    train_loss,

                "validation":
                    val_metrics,
            }
        )

        if (
            validation_ap
            > best_ap
        ):

            best_ap = (
                validation_ap
            )

            epochs_without_improvement = 0

            save_checkpoint(
                system,
                config,
            )

            print(
                "New best checkpoint saved."
            )

        else:

            epochs_without_improvement += 1

            print(
                "No validation improvement: "
                f"{epochs_without_improvement}"
                f"/{PATIENCE}"
            )

            if (
                epochs_without_improvement
                >= PATIENCE
            ):

                print(
                    "\nEarly stopping."
                )

                break

    # ======================================================
    # 5.8 FINAL EVALUATION
    #
    # Load best parameters.
    # Reconstruct graph state from scratch.
    # ======================================================

    print(
        "\nLoading best checkpoint..."
    )

    checkpoint = load_checkpoint(
        system,
        device,
    )

    reset_system(
        system
    )

    system.memory.eval()
    system.gnn.eval()
    system.classifier.eval()

    # Build historical memory ONLY from train.
    print(
        "\nReplaying training history..."
    )

    replay_split(
        bundle,
        system,
        device,
        "train",
    )

    # Score validation again using best model.
    print(
        "Scoring validation..."
    )

    y_val, val_scores = (
        evaluate_split(
            bundle,
            system,
            device,
            "validation",
        )
    )

    final_val_metrics = (
        evaluate_scores(
            y_val,
            val_scores,
        )
    )

    # Validation has now entered memory.
    # The locked test split remains untouched during Phase 10 candidate
    # selection. Enable it only once for the final selected model.

    y_test = None
    test_scores = None
    final_test_metrics = None

    if EVAL_TEST:

        print(
            "Scoring untouched test..."
        )

        y_test, test_scores = (
            evaluate_split(
                bundle,
                system,
                device,
                "test",
            )
        )

        final_test_metrics = (
            evaluate_scores(
                y_test,
                test_scores,
            )
        )

    print(
        "\n--- FINAL VALIDATION ---"
    )

    print(
        "AP:",
        final_val_metrics[
            "average_precision"
        ],
    )

    print(
        "Recall@1%:",
        final_val_metrics[
            "recall_at_top_1pct"
        ],
    )

    if EVAL_TEST:

        print(
            "\n--- FINAL TEST ---"
        )

        print(
            "AP:",
            final_test_metrics[
                "average_precision"
            ],
        )

        print(
            "Recall@1%:",
            final_test_metrics[
                "recall_at_top_1pct"
            ],
        )

    else:

        print(
            "\nLOCKED_TEST_EVALUATION=SKIPPED"
        )

    # ======================================================
    # Save predictions
    # ======================================================

    pl.DataFrame(
        {
            "transaction_id":
                bundle.ids[
                    "validation"
                ],

            "is_laundering":
                y_val,

            "tgn_risk_score":
                val_scores,
        }
    ).write_parquet(
        PREDICTION_DIR
        / "tgn_validation_predictions.parquet",
        compression="zstd",
    )

    if EVAL_TEST:

        pl.DataFrame(
            {
                "transaction_id":
                    bundle.ids[
                        "test"
                    ],

                "is_laundering":
                    y_test,

                "tgn_risk_score":
                    test_scores,
            }
        ).write_parquet(
            PREDICTION_DIR
            / "tgn_test_predictions.parquet",
            compression="zstd",
        )

    report = {
        "model":
            "TGN",

        "selection_metric":
            "validation_average_precision",

        "best_validation_ap":
            best_ap,

        "config":
            checkpoint[
                "config"
            ],

        "training_history":
            history,

        "final_validation":
            final_val_metrics,

        "test_evaluated":
            EVAL_TEST,

        "final_test":
            final_test_metrics,
    }

    with open(
        REPORT_DIR
        / "tgn_metrics.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            report,
            file,
            indent=2,
        )

    print(
        "\nSaved:"
    )

    print(
        CHECKPOINT_PATH
    )

    print(
        REPORT_DIR
        / "tgn_metrics.json"
    )

    print(
        "TEST_USED_FOR_SELECTION=FALSE"
    )

    print(
        "LOCKED_TEST_EVALUATED="
        + ("TRUE" if EVAL_TEST else "FALSE")
    )


if __name__ == "__main__":
    main()