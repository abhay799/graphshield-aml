# System Overview

This is the repository-native, high-level view of GraphShield AML. Solid paths describe the implemented local workflow. The dashed box contains optional/provisioned infrastructure and is not evidence of a live deployment.

```mermaid
flowchart TB
    raw[Synthetic IBM AML transactions] --> canon[Canonical ingestion and normalization]
    canon --> silver[Silver transaction dataset]
    silver --> pit[Chronological and point-in-time processing]
    pit --> features[Transaction, entity, and graph features]
    features --> risk[Rules, tabular ML, and graph intelligence]
    silver --> tgn[Temporal events and TGN intelligence]
    risk --> fusion[Frozen calibration/fusion and risk ranking]
    tgn --> fusion
    fusion --> queue[Analyst case queue]
    queue --> investigation[Case bundles, subgraphs, paths, and evidence]
    investigation --> explain[Phase 11 explanation]
    investigation --> policy[Case and policy retrieval]
    explain --> agent[Phase 12 bounded investigation assistance]
    policy --> agent
    agent --> human[Human investigator review and decision]
    human --> governance[Feedback, audit, drift, and human-gated governance]

    api[FastAPI services] --> workbench[Streamlit analyst workbench]
    queue -. served through .-> api
    explain -. served through .-> api
    agent -. served through .-> api
    governance -. served through .-> api

    runtime[Artifact manifests, integrity gates, health/readiness, logging/metrics] -. runtime contracts .-> api
    deploy[Docker and Kubernetes configuration] -. deployment contracts .-> runtime

    subgraph optional[OPTIONAL / PROVISIONED / NOT PROVEN LIVE]
        neo4j[Neo4j]
        mlflow[MLflow and MinIO]
        streaming[Redis and Redpanda]
        observe[Prometheus and Grafana]
        identity[Keycloak]
    end
```

The local core uses Parquet, DuckDB/SQLite, model artifacts, and code under `src/`. Optional services are Compose-profile configuration, not demonstrated live dependencies. See [Project Architecture](PROJECT_ARCHITECTURE.md) and [Limitations](../LIMITATIONS.md).
