from collections import Counter
from pathlib import Path

import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EDGE_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "transaction_edges.parquet"
)

SPLIT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "gold"
    / "model_features_v1_split.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "connected_components_train_snapshot.parquet"
)


SNAPSHOT_SPLIT = "train"


class UnionFind:

    def __init__(self):
        self.parent = {}
        self.size = {}

    def add(self, x):

        if x not in self.parent:
            self.parent[x] = x
            self.size[x] = 1

    def find(self, x):

        self.add(x)

        root = x

        while self.parent[root] != root:
            root = self.parent[root]

        while self.parent[x] != x:
            parent = self.parent[x]
            self.parent[x] = root
            x = parent

        return root

    def union(self, a, b):

        root_a = self.find(a)
        root_b = self.find(b)

        if root_a == root_b:
            return

        if self.size[root_a] < self.size[root_b]:
            root_a, root_b = root_b, root_a

        self.parent[root_b] = root_a
        self.size[root_a] += self.size[root_b]


def main():

    print("=" * 90)
    print("GraphShield AML - Connected Components")
    print("=" * 90)

    cutoff = (
        pl.scan_parquet(SPLIT_PATH)
        .filter(
            pl.col("split")
            == SNAPSHOT_SPLIT
        )
        .select(
            pl.col("event_ts").max()
        )
        .collect()
        .item()
    )

    print("\nSnapshot cutoff:")
    print(cutoff)

    pairs = (
        pl.scan_parquet(EDGE_PATH)
        .filter(
            pl.col("event_ts") <= cutoff
        )
        .select(
            [
                pl.when(
                    pl.col("from_account_key")
                    <= pl.col("to_account_key")
                )
                .then(pl.col("from_account_key"))
                .otherwise(pl.col("to_account_key"))
                .alias("node_a"),

                pl.when(
                    pl.col("from_account_key")
                    <= pl.col("to_account_key")
                )
                .then(pl.col("to_account_key"))
                .otherwise(pl.col("from_account_key"))
                .alias("node_b"),
            ]
        )
        .unique()
        .sort(
            [
                "node_a",
                "node_b",
            ]
        )
        .collect()
    )

    print(
        f"\nUnique undirected relationships: "
        f"{pairs.height:,}"
    )

    uf = UnionFind()

    for node_a, node_b in pairs.iter_rows():
        uf.union(node_a, node_b)

    roots = {
        node: uf.find(node)
        for node in uf.parent
    }

    component_sizes = Counter(
        roots.values()
    )

    unique_roots = sorted(
        component_sizes
    )

    component_ids = {
        root: index + 1
        for index, root
        in enumerate(unique_roots)
    }

    output = pl.DataFrame(
        {
            "account_key": list(
                roots.keys()
            ),

            "component_id": [
                component_ids[root]
                for root in roots.values()
            ],

            "component_size": [
                component_sizes[root]
                for root in roots.values()
            ],
        }
    ).with_columns(
        pl.lit(cutoff)
        .alias("snapshot_cutoff")
    )

    output.write_parquet(
        OUTPUT_PATH,
        compression="zstd",
    )

    print(
        f"\nComponents: "
        f"{len(component_sizes):,}"
    )

    print(
        f"Largest component: "
        f"{max(component_sizes.values()):,}"
    )

    print("\nCreated:")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()