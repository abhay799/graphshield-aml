# Graph Investigation Flow

```mermaid
flowchart TB
    tx[Normalized transactions] --> edges[Sender/receiver account edges]
    edges --> network[Local account/entity network]
    network --> features[Point-in-time degree, history, pair, and concentration features]
    network --> community[Louvain community analysis\nPhase 9]
    network --> propagation[Three-hop account-risk propagation\nPhase 9]
    network --> motifs[Rapid pass-through and two-node-cycle signals\nPhase 9]
    features --> context[Suspicious network context]
    community --> context
    propagation --> context
    motifs --> context
    context --> casegraph[Case-specific point-in-time subgraph]
    casegraph --> paths[Path extraction]
    paths --> evidence[Investigator graph evidence]

    optional[Optional Neo4j loaders and Compose profile\nNOT PROVEN LIVE] -. optional integration .-> network
```

The demonstrated core is local graph intelligence built from repository tables and NetworkX community analysis. Neo4j is an optional integration, not a required or proven-live component of this flow.
