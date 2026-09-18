# Phase Index

## Reading this index

Statuses reflect repository evidence: source modules, tests, validation/certification reports, and Git history. A stored certification is historical evidence, not a fresh verification performed when this document is read.

For the dependency view, see [Phase Architecture](PHASE_ARCHITECTURE.md).

There is no formal Phase 0 definition, implementation, or certification in the repository. The `84050dd` initial commit is therefore listed only as **bootstrap/history**.

| Stage | Name | Evidence summary | Status |
|---|---|---|---|
| Bootstrap/history | Initial project structure | Git commit `84050dd`; no formal Phase 0 artifact | NOT FOUND as a formal phase |
| 1 | Data foundation | Canonical/silver pipeline, data-quality and Phase 1 validation, Phases 1–6 certification | IMPLEMENTED + VERIFIED historically |
| 2 | Features and rules | Feature/rule builders, leakage/entity-overlap validation, certification | IMPLEMENTED + VERIFIED historically |
| 3 | Baseline ML | Logistic, LightGBM, CatBoost training/calibration/selection scripts and reports | IMPLEMENTED + VERIFIED historically |
| 4 | Graph intelligence | Graph tables, degree/pair/concentration/bank features and validation | IMPLEMENTED + VERIFIED historically |
| 5 | Temporal GNN / fusion | TGN event/training/fusion modules, metrics, Phase 5 report | IMPLEMENTED + VERIFIED historically |
| 6 | Investigation and RAG | Case/evidence/retrieval modules, grounding and RAG reports | IMPLEMENTED + VERIFIED historically |
| 7 | Service/workbench integration | FastAPI, analyst state, workbench, integration tests and certification | IMPLEMENTED + VERIFIED historically |
| 8 | Productization | Docker/Compose, observability, security headers, CI/demo assets, certification | IMPLEMENTED BUT NOT FULLY VERIFIED currently |
| 8.5 | Platform foundation | Replay, profiles, observability/MLOps/security/Neo4j foundations and report | IMPLEMENTED BUT NOT FULLY VERIFIED currently |
| 9 | Advanced online graph intelligence | Online consumer, risk propagation, communities, motifs, optional Neo4j loaders and reports | IMPLEMENTED BUT NOT FULLY VERIFIED currently |
| 10 | Real-time streaming + temporal fusion | Replay scoring, parity/live scoring, frozen fusion and locked-test certification artifact | IMPLEMENTED + VERIFIED historically |
| 11 | Explainable AML | Explanation service/evidence, API routes, dedicated tests and certification | IMPLEMENTED + VERIFIED historically |
| 12 | Agentic investigation | Bounded tools, grounding/audit modules, API routes, dedicated tests and certification | IMPLEMENTED + VERIFIED historically |
| 13 | Feedback, drift, MLOps governance | Append-only feedback, monitors/gates, API routes, dedicated tests and certification | IMPLEMENTED + VERIFIED historically |
| 14 | Enterprise platform/cloud readiness | Artifact integrity, K8s contracts, readiness/release controls, dedicated tests and certification | IMPLEMENTED + VERIFIED historically |
| 15 | Reliability/final release | SLO-readiness, failure/recovery/release gates, dedicated tests and certification | IMPLEMENTED + VERIFIED historically |

## Historical certification references

- Phases 1–6: `reports/final/phases_1_6_certification.md`
- Phase 7: `reports/final/phase7_certification.md`
- Phase 8: `reports/final/phase8_certification.md`
- Phase 10: `reports/v2/phase10/phase10_certification_v1.json`
- Phases 11–15: `reports/v2/phase11` through `reports/v2/phase15`

Phase 9 reports are under `reports/v2/phase9`; Phase 8.5 evidence includes source/configuration and a locally present historical report. Refer to [Validation](../VALIDATION.md) for what these reports do—and do not—establish.
