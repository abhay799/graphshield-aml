from pathlib import Path

import polars as pl
import torch

from torch_geometric.data import TemporalData

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


SMOKE_EVENTS = 20_000


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
            +
            time_enc.out_channels
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


def main():

    print("=" * 90)
    print("GraphShield AML - TGN Smoke Test")
    print("=" * 90)

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print("\nDevice:")
    print(device)

    # ======================================================
    # Load ONLY a small sample
    # ======================================================

    df = (
        pl.scan_parquet(
            EVENT_PATH
        )
        .head(
            SMOKE_EVENTS
        )
        .select(
            [
                "src",
                "dst",
                "t_seconds",
                *MESSAGE_COLUMNS,
                "is_laundering",
            ]
        )
        .collect()
    )

    num_nodes = (
        pl.scan_parquet(
            NODE_PATH
        )
        .select(pl.len())
        .collect()
        .item()
    )

    src = torch.tensor(
        df["src"].to_numpy(),
        dtype=torch.long,
    )

    dst = torch.tensor(
        df["dst"].to_numpy(),
        dtype=torch.long,
    )

    t = torch.tensor(
        df["t_seconds"].to_numpy(),
        dtype=torch.long,
    )

    msg = torch.tensor(
        df.select(
            MESSAGE_COLUMNS
        )
        .to_numpy(),
        dtype=torch.float32,
    )

    y = torch.tensor(
        df[
            "is_laundering"
        ]
        .to_numpy(),
        dtype=torch.float32,
    )

    # ======================================================
    # PyG TemporalData
    # ======================================================

    data = TemporalData(
        src=src,
        dst=dst,
        t=t,
        msg=msg,
        y=y,
    )

    print("\nTemporalData:")
    print(data)

    print(
        "\nEvents:",
        data.num_events,
    )

    print(
        "Nodes in mapping:",
        num_nodes,
    )

    print(
        "Message dimension:",
        data.msg.size(1),
    )

    print(
        "Positive labels:",
        int(
            data.y.sum().item()
        ),
    )

    # ======================================================
    # TGN components
    # ======================================================

    memory_dim = 32
    time_dim = 16
    embedding_dim = 32

    memory = TGNMemory(
        num_nodes=num_nodes,

        raw_msg_dim=(
            data.msg.size(-1)
        ),

        memory_dim=memory_dim,

        time_dim=time_dim,

        message_module=IdentityMessage(
            data.msg.size(-1),
            memory_dim,
            time_dim,
        ),

        aggregator_module=(
            LastAggregator()
        ),
    ).to(device)

    neighbor_loader = (
        LastNeighborLoader(
            num_nodes=num_nodes,

            size=10,

            device=device,
        )
    )

    gnn = GraphAttentionEmbedding(
        in_channels=memory_dim,

        out_channels=embedding_dim,

        msg_dim=(
            data.msg.size(-1)
        ),

        time_enc=(
            memory.time_enc
        ),
    ).to(device)

    classifier = RiskClassifier(
        embedding_dim,
        data.msg.size(-1),
    ).to(device)

    print(
        "\nTGN memory created."
    )

    print(
        "Memory dimension:",
        memory_dim,
    )

    print(
        "Embedding dimension:",
        embedding_dim,
    )

    print(
        "Neighbor history size:",
        10,
    )

    # ======================================================
    # Test first timestamp group
    #
    # IMPORTANT:
    # all transactions at same timestamp are scored BEFORE
    # any of them are inserted into memory.
    # ======================================================

    first_t = t[0]

    mask = (
        t == first_t
    )

    batch_src = (
        src[mask]
        .to(device)
    )

    batch_dst = (
        dst[mask]
        .to(device)
    )

    batch_t = (
        t[mask]
        .to(device)
    )

    batch_msg = (
        msg[mask]
        .to(device)
    )

    n_id = torch.cat(
        [
            batch_src,
            batch_dst,
        ]
    ).unique()

    n_id, edge_index, e_id = (
        neighbor_loader(
            n_id
        )
    )

    assoc = torch.empty(
        num_nodes,
        dtype=torch.long,
        device=device,
    )

    assoc[n_id] = torch.arange(
        n_id.size(0),
        device=device,
    )

    # Historical memory BEFORE current event
    z, last_update = memory(
        n_id
    )

    # First timestamp has no historical graph edges.
    if edge_index.numel() > 0:

        history_t = (
            t[e_id.cpu()]
            .to(device)
        )

        history_msg = (
            msg[e_id.cpu()]
            .to(device)
        )

        z = gnn(
            z,
            last_update,
            edge_index,
            history_t,
            history_msg,
        )

    logits = classifier(
        z[
            assoc[
                batch_src
            ]
        ],

        z[
            assoc[
                batch_dst
            ]
        ],

        batch_msg,
    )

    probabilities = (
        torch.sigmoid(
            logits
        )
    )

    print(
        "\nFirst timestamp events:",
        batch_src.size(0),
    )

    print(
        "Risk output shape:",
        probabilities.shape,
    )

    print(
        "First 5 risk scores:",
        probabilities[
            :5
        ]
        .detach()
        .cpu()
        .numpy(),
    )

    # ======================================================
    # AFTER prediction → update memory
    # ======================================================

    memory.update_state(
        batch_src,
        batch_dst,
        batch_t,
        batch_msg,
    )

    neighbor_loader.insert(
        batch_src,
        batch_dst,
    )

    print(
        "\nMemory update succeeded."
    )

    print("\n" + "=" * 90)
    print("TGN SMOKE TEST PASSED")
    print("=" * 90)


if __name__ == "__main__":
    main()