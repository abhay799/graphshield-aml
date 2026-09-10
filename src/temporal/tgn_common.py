from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
import torch

from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    roc_auc_score,
)

from torch_geometric.nn import (
    TGNMemory,
    TransformerConv,
)

from torch_geometric.nn.models.tgn import (
    IdentityMessage,
    LastAggregator,
    LastNeighborLoader,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVENT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
    / "tgn_events.parquet"
)

NODE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "temporal"
    / "tgn_node_mapping.parquet"
)


MESSAGE_COLUMNS = [
    "log_amount_paid",
    "log_amount_received",
    "cross_bank",
    "cross_currency",
    "same_currency_amount_ratio",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]


@dataclass
class EventBundle:

    src: torch.Tensor
    dst: torch.Tensor
    t: torch.Tensor
    msg: torch.Tensor
    y: torch.Tensor

    ranges: dict
    groups: dict
    ids: dict

    num_nodes: int


class GraphAttentionEmbedding(
    torch.nn.Module
):

    def __init__(
        self,
        in_channels,
        out_channels,
        msg_dim,
        time_enc,
    ):

        super().__init__()

        self.time_enc = time_enc

        edge_dim = (
            msg_dim
            + time_enc.out_channels
        )

        self.conv = TransformerConv(
            in_channels,
            out_channels // 2,
            heads=2,
            dropout=0.1,
            edge_dim=edge_dim,
        )

    def forward(
        self,
        x,
        last_update,
        edge_index,
        t,
        msg,
    ):

        if edge_index.numel() == 0:
            return x

        relative_time = (
            last_update[
                edge_index[0]
            ]
            - t
        )

        relative_time_encoding = (
            self.time_enc(
                relative_time.to(
                    x.dtype
                )
            )
        )

        edge_attr = torch.cat(
            [
                relative_time_encoding,
                msg,
            ],
            dim=-1,
        )

        return self.conv(
            x,
            edge_index,
            edge_attr,
        )


class RiskClassifier(
    torch.nn.Module
):

    def __init__(
        self,
        embedding_dim,
        msg_dim,
    ):

        super().__init__()

        input_dim = (
            embedding_dim * 2
            + msg_dim
        )

        self.network = torch.nn.Sequential(
            torch.nn.Linear(
                input_dim,
                64,
            ),

            torch.nn.ReLU(),

            torch.nn.Dropout(
                0.20
            ),

            torch.nn.Linear(
                64,
                32,
            ),

            torch.nn.ReLU(),

            torch.nn.Linear(
                32,
                1,
            ),
        )

    def forward(
        self,
        z_src,
        z_dst,
        msg,
    ):

        x = torch.cat(
            [
                z_src,
                z_dst,
                msg,
            ],
            dim=-1,
        )

        return (
            self.network(x)
            .view(-1)
        )


@dataclass
class TGNSystem:

    memory: TGNMemory
    neighbor_loader: LastNeighborLoader
    gnn: GraphAttentionEmbedding
    classifier: RiskClassifier
    assoc: torch.Tensor


def make_groups(
    t: torch.Tensor,
    start: int,
    end: int,
):

    values = (
        t[start:end]
        .numpy()
    )

    if len(values) == 0:
        return []

    starts = np.concatenate(
        [
            np.array(
                [0],
                dtype=np.int64,
            ),

            (
                np.flatnonzero(
                    values[1:]
                    != values[:-1]
                )
                + 1
            ),
        ]
    )

    ends = np.concatenate(
        [
            starts[1:],

            np.array(
                [len(values)],
                dtype=np.int64,
            ),
        ]
    )

    return [
        (
            start + int(s),
            start + int(e),
        )
        for s, e
        in zip(
            starts,
            ends,
        )
    ]


def _load_split(
    split_name,
    max_events=None,
):

    lf = (
        pl.scan_parquet(
            EVENT_PATH
        )
        .filter(
            pl.col("split")
            == split_name
        )
        .select(
            [
                "transaction_id",

                "src",
                "dst",
                "t_seconds",

                *MESSAGE_COLUMNS,

                "is_laundering",
            ]
        )
    )

    if (
        max_events is not None
        and max_events > 0
    ):
        lf = lf.head(
            max_events
        )

    return lf.collect()


def load_event_bundle(
    max_train_events=None,
    max_val_events=None,
    max_test_events=None,
):

    print("\nLoading temporal events...")

    train = _load_split(
        "train",
        max_train_events,
    )

    validation = _load_split(
        "validation",
        max_val_events,
    )

    test = _load_split(
        "test",
        max_test_events,
    )

    frames = [
        train,
        validation,
        test,
    ]

    lengths = [
        frame.height
        for frame in frames
    ]

    combined = pl.concat(
        frames,
        how="vertical",
    )

    src = torch.tensor(
        combined[
            "src"
        ].to_numpy(),
        dtype=torch.long,
    )

    dst = torch.tensor(
        combined[
            "dst"
        ].to_numpy(),
        dtype=torch.long,
    )

    t = torch.tensor(
        combined[
            "t_seconds"
        ].to_numpy(),
        dtype=torch.long,
    )

    msg = torch.tensor(
        combined.select(
            MESSAGE_COLUMNS
        ).to_numpy(),
        dtype=torch.float32,
    )

    y = torch.tensor(
        combined[
            "is_laundering"
        ].to_numpy(),
        dtype=torch.float32,
    )

    train_end = lengths[0]

    validation_end = (
        train_end
        + lengths[1]
    )

    test_end = (
        validation_end
        + lengths[2]
    )

    ranges = {
        "train": (
            0,
            train_end,
        ),

        "validation": (
            train_end,
            validation_end,
        ),

        "test": (
            validation_end,
            test_end,
        ),
    }

    groups = {
        name: make_groups(
            t,
            start,
            end,
        )
        for name, (
            start,
            end,
        )
        in ranges.items()
    }

    ids = {
        "validation":
            validation[
                "transaction_id"
            ].to_list(),

        "test":
            test[
                "transaction_id"
            ].to_list(),
    }

    num_nodes = (
        pl.scan_parquet(
            NODE_PATH
        )
        .select(
            pl.len()
        )
        .collect()
        .item()
    )

    print(
        f"Train events:      "
        f"{lengths[0]:,}"
    )

    print(
        f"Validation events: "
        f"{lengths[1]:,}"
    )

    print(
        f"Test events:       "
        f"{lengths[2]:,}"
    )

    print(
        f"Nodes:             "
        f"{num_nodes:,}"
    )

    print(
        f"Train timestamps:  "
        f"{len(groups['train']):,}"
    )

    return EventBundle(
        src=src,
        dst=dst,
        t=t,
        msg=msg,
        y=y,
        ranges=ranges,
        groups=groups,
        ids=ids,
        num_nodes=num_nodes,
    )


def build_system(
    bundle,
    device,
    memory_dim=32,
    time_dim=16,
    embedding_dim=32,
    neighbor_size=10,
):

    if memory_dim != embedding_dim:
        raise ValueError(
            "For this implementation, "
            "memory_dim must equal embedding_dim."
        )

    message_dim = (
        bundle.msg.size(1)
    )

    memory = TGNMemory(
        num_nodes=bundle.num_nodes,

        raw_msg_dim=message_dim,

        memory_dim=memory_dim,

        time_dim=time_dim,

        message_module=IdentityMessage(
            message_dim,
            memory_dim,
            time_dim,
        ),

        aggregator_module=(
            LastAggregator()
        ),
    ).to(device)

    neighbor_loader = (
        LastNeighborLoader(
            num_nodes=bundle.num_nodes,
            size=neighbor_size,
            device=device,
        )
    )

    gnn = GraphAttentionEmbedding(
        in_channels=memory_dim,
        out_channels=embedding_dim,
        msg_dim=message_dim,
        time_enc=memory.time_enc,
    ).to(device)

    classifier = RiskClassifier(
        embedding_dim=embedding_dim,
        msg_dim=message_dim,
    ).to(device)

    assoc = torch.empty(
        bundle.num_nodes,
        dtype=torch.long,
        device=device,
    )

    return TGNSystem(
        memory=memory,
        neighbor_loader=neighbor_loader,
        gnn=gnn,
        classifier=classifier,
        assoc=assoc,
    )


def reset_system(
    system,
):

    system.memory.reset_state()

    system.neighbor_loader.reset_state()


def model_parameters(
    system,
):

    # memory.time_enc is shared with the GNN,
    # so use a set to avoid duplicate parameters.

    parameters = (
        set(
            system.memory.parameters()
        )
        |
        set(
            system.gnn.parameters()
        )
        |
        set(
            system.classifier.parameters()
        )
    )

    return list(
        parameters
    )


def score_group(
    bundle,
    system,
    device,
    start,
    end,
):

    src = (
        bundle.src[start:end]
        .to(device)
    )

    dst = (
        bundle.dst[start:end]
        .to(device)
    )

    t = (
        bundle.t[start:end]
        .to(device)
    )

    msg = (
        bundle.msg[start:end]
        .to(device)
    )

    y = (
        bundle.y[start:end]
        .to(device)
    )

    seed_nodes = torch.cat(
        [
            src,
            dst,
        ]
    ).unique()

    n_id, edge_index, e_id = (
        system.neighbor_loader(
            seed_nodes
        )
    )

    system.assoc[
        n_id
    ] = torch.arange(
        n_id.size(0),
        device=device,
    )

    z, last_update = (
        system.memory(
            n_id
        )
    )

    if edge_index.numel() > 0:

        history_indices = (
            e_id
            .detach()
            .cpu()
        )

        history_t = (
            bundle.t[
                history_indices
            ]
            .to(device)
        )

        history_msg = (
            bundle.msg[
                history_indices
            ]
            .to(device)
        )

        z = system.gnn(
            z,
            last_update,
            edge_index,
            history_t,
            history_msg,
        )

    z_src = z[
        system.assoc[src]
    ]

    z_dst = z[
        system.assoc[dst]
    ]

    logits = (
        system.classifier(
            z_src,
            z_dst,
            msg,
        )
    )

    return (
        src,
        dst,
        t,
        msg,
        y,
        logits,
        z_src,
        z_dst,
    )


def update_group(
    system,
    src,
    dst,
    t,
    msg,
):

    system.memory.update_state(
        src,
        dst,
        t,
        msg,
    )

    system.neighbor_loader.insert(
        src,
        dst,
    )


@torch.no_grad()
def replay_split(
    bundle,
    system,
    device,
    split_name,
):

    system.memory.eval()
    system.gnn.eval()
    system.classifier.eval()

    for start, end in (
        bundle.groups[
            split_name
        ]
    ):

        src = (
            bundle.src[
                start:end
            ]
            .to(device)
        )

        dst = (
            bundle.dst[
                start:end
            ]
            .to(device)
        )

        t = (
            bundle.t[
                start:end
            ]
            .to(device)
        )

        msg = (
            bundle.msg[
                start:end
            ]
            .to(device)
        )

        # Access current state before inserting this
        # timestamp group.
        touched = torch.cat(
            [
                src,
                dst,
            ]
        ).unique()

        system.memory(
            touched
        )

        update_group(
            system,
            src,
            dst,
            t,
            msg,
        )


@torch.no_grad()
def evaluate_split(
    bundle,
    system,
    device,
    split_name,
):

    system.memory.eval()
    system.gnn.eval()
    system.classifier.eval()

    scores = []
    labels = []

    for start, end in (
        bundle.groups[
            split_name
        ]
    ):

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

        probability = (
            torch.sigmoid(
                logits
            )
            .detach()
            .cpu()
        )

        scores.append(
            probability
        )

        labels.append(
            y.detach().cpu()
        )

        # Only after all events at this timestamp
        # have been scored.
        update_group(
            system,
            src,
            dst,
            t,
            msg,
        )

    return (
        torch.cat(labels)
        .numpy()
        .astype(np.int8),

        torch.cat(scores)
        .numpy(),
    )


def evaluate_scores(
    y_true,
    scores,
):

    y_true = np.asarray(
        y_true
    )

    scores = np.asarray(
        scores
    )

    results = {
        "rows": int(
            len(y_true)
        ),

        "positives": int(
            y_true.sum()
        ),

        "prevalence": float(
            y_true.mean()
        ),

        "average_precision": float(
            average_precision_score(
                y_true,
                scores,
            )
        ),

        "brier_score": float(
            brier_score_loss(
                y_true,
                np.clip(
                    scores,
                    0,
                    1,
                ),
            )
        ),
    }

    try:

        results[
            "roc_auc"
        ] = float(
            roc_auc_score(
                y_true,
                scores,
            )
        )

    except ValueError:

        results[
            "roc_auc"
        ] = None

    ranking = np.argsort(
        scores
    )[::-1]

    total_positive = max(
        int(
            y_true.sum()
        ),
        1,
    )

    prevalence = max(
        float(
            y_true.mean()
        ),
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

        captured = int(
            y_true[
                selected
            ].sum()
        )

        precision = (
            captured / n
        )

        recall = (
            captured
            / total_positive
        )

        lift = (
            precision
            / prevalence
        )

        name = (
            f"{int(fraction * 100)}pct"
        )

        results[
            f"precision_at_top_{name}"
        ] = float(
            precision
        )

        results[
            f"recall_at_top_{name}"
        ] = float(
            recall
        )

        results[
            f"lift_at_top_{name}"
        ] = float(
            lift
        )

    return results


def parameter_state(
    module,
):

    return {
        name:
            parameter
            .detach()
            .cpu()
            .clone()

        for name, parameter
        in module.named_parameters()
    }


def load_parameter_state(
    module,
    state,
):

    parameters = dict(
        module.named_parameters()
    )

    for name, value in (
        state.items()
    ):

        parameters[
            name
        ].data.copy_(
            value.to(
                parameters[
                    name
                ].device
            )
        )