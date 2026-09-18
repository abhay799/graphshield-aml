# Limitations

## Research and decision-support scope

GraphShield is a portfolio/research prototype. It must not be represented as a deployed banking system, a regulatory-certified product, legal advice, an autonomous compliance engine, or a guarantee of AML/fraud detection. Human investigators retain authority over review, disposition, and any external action.

## Data limitations

The declared core source is synthetic IBM AML-Data LI-Small. Public policy documents are locally processed for retrieval. Neither fact establishes suitability for real customer data, regulated operations, or any jurisdiction-specific compliance programme.

The repository intentionally ignores `data/**`, model binaries, checkpoints, SQLite/DB state, and several generated artifacts. Local files can support a demonstration, but a fresh clone is not sufficient to reproduce the full runtime without an authorized artifact/data handoff.

## Artifact and environment reproducibility

Historical manifests reference artifacts that are present locally but untracked. The project also contains old/stale artifact filenames alongside current paths; manifests and phase reports should determine provenance, not a filename alone.

Environment evidence is inconsistent: Docker/CI specify Python 3.12, while historical certification snapshots record Python 3.14.5. Dependency files are pinned, but there is no single lockfile or committed artifact registry that makes the full historical environment independently reproducible.

## Model limitations

The model history contains multiple successive candidates and report scopes. Older CatBoost selection evidence, a Phase 5 graph-LightGBM manifest, and a later Phase 10 graph/TGN-fusion candidate should not be merged into one unqualified performance claim. Metrics in reports are historical evaluation outputs on synthetic data and must be read with their split and selection policy.

The TGN is a temporal research component. Explanation deliberately does not imply TGN SHAP attribution. Risk scores and queues prioritize investigation effort; they do not establish suspicious activity, criminal conduct, or a reporting obligation.

## Retrieval and agent limitations

The policy corpus supports cited contextual retrieval, not legal interpretation or a proof of current regulatory completeness. Source freshness must be independently checked before any regulated use.

The Phase 12 agent is bounded and read-only, but its grounded response is still investigation assistance. A citation does not replace investigator verification, and a fail-closed behavior only addresses the documented grounding contract.

## Platform and operational limitations

Docker, Kubernetes, monitoring, streaming, MLOps, identity, graph-database, and cloud-adjacent components include configuration or integration code. They are not evidence of a deployed or continuously operated environment. Redis, Redpanda, MinIO, MLflow, Prometheus, Grafana, Keycloak, and Neo4j are Compose-profile services, not demonstrated live dependencies in this repository state.

Readiness/liveness, artifact-integrity, recovery, HPA/PDB, and release gates establish contracts. The stored Phase 15 smoke test is in-process and does not prove production networking, traffic load, availability, latency, resilience, or incident response.

## Validation limitations

Stored certifications are historical artifacts. The active CI workflow is lightweight, does not run the full test suite, and is configured for `master`/`main` rather than the recovered `graphshield-v2` branch. A future release should run and record fresh checks in its own environment rather than relying on this documentation or historical reports.

## Documentation boundary

This documentation explains repository evidence as recovered. It does not alter Phase 1–15 code, tests, artifacts, or runtime behavior, and it does not begin a subsequent productization step.
