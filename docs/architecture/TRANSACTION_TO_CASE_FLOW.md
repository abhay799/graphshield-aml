# Transaction-to-Case Flow

```mermaid
flowchart LR
    raw[Synthetic raw transaction] --> schema[Canonical schema and normalization]
    schema --> silver[Silver transactions\nParquet]
    silver --> split[Chronological splits and point-in-time processing]
    split --> tx[Transaction/history/velocity features\nParquet]
    split --> entity[Counterparty/entity features\nParquet]
    split --> graph[Graph features\nParquet]
    tx --> rules[Rules]
    tx --> scores[Tabular model artifacts and scores]
    entity --> scores
    graph --> scores
    split --> tgn[Temporal events and TGN artifacts]
    scores --> rank[Frozen calibration/fusion and ranking]
    tgn --> rank
    rank --> queue[Case queue\nParquet]
    queue --> store[Case store\nDuckDB]
    store --> bundle[Case bundle, subgraph, paths, and evidence]
    bundle --> analyst[Analyst review state\nSQLite]
    rank -. artifact references .-> manifest[Certification and integrity manifests]
```

This is an artifact-oriented local pipeline. The raw and processed data, model binaries, and operational stores are intentionally Git-ignored; their local presence does not make a fresh clone runnable without an authorized artifact handoff.
