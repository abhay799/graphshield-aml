# Artifact Handoff

This document defines the minimum artifact handoff needed to run GraphShield AML from a fresh checkout without treating the entire local `data/**` tree as required. The list is derived from current runtime consumers under `src/`, plus the strict readiness contract.

## A. Git-tracked material

A normal checkout already contains the repository material needed to understand and execute the codebase itself, including:

- source code under `src/`
- API, service, retrieval, explainability, governance, and enterprise runtime modules
- configuration files such as `pyproject.toml`, Docker/Compose configuration, and pytest configuration
- tests under `tests/`
- CI/test fixture generation code under `scripts/ci/`
- documentation under `docs/`
- non-sensitive reports and certification evidence that are tracked in Git, including the Phase 10 and Phase 13 certification JSON files referenced by current runtime/readiness code

The CPU/demo/API/test dependency contract is defined by:

- `requirements-repro.in`
- `requirements-repro.lock.txt`

A fresh clone still needs the out-of-band runtime artifacts in section B for the full analyst demo.

### Optional live-scoring dependency scope

The CPU/demo/API/test reproducibility contract above does **not** include the optional live-scoring runtime dependencies. Live transaction scoring is a separate capability with its own dependency file, `requirements-live-scoring.txt`, and requires Redis at runtime.

The live-scoring dependency scope is intentionally separate from `requirements-repro.in` / `requirements-repro.lock.txt`; it must not be treated as part of the core reproducible demo contract established by the clean Python 3.12 verification. Enabling live scoring adds an optional Redis-backed runtime surface, while the core analyst/demo/test reproducibility contract remains unchanged.

## B. Out-of-band runtime artifacts

These files are not assumed to be present in a fresh Git checkout. Only the runtime artifacts consumed by current code paths are listed here.

| Relative path | Role | Required / optional | Consuming component | SHA-256 |
| --- | --- | --- | --- | --- |
| `data/processed/cases/case_queue.parquet` | Authoritative analyst case queue used for case lookup, queue listing, graph metadata, and case-to-transaction resolution. | Required for the analyst API/demo. | `services.graphshield_service.GraphShieldService`, `services.case_graph_service.CaseGraphService`, `explainability.case_explanation.Phase11CaseExplanationService` | not computed |
| `data/processed/cases/evidence_documents.parquet` | Case evidence corpus used for deterministic case overview, path/history evidence, and evidence search results. | Required for the analyst API/demo. | `retrieval.retriever.EvidenceRetriever` | not computed |
| `data/processed/cases/evidence_tfidf_index.joblib` | TF-IDF vectorizer/matrix plus case/evidence identifiers used for case evidence retrieval. | Required for evidence search and current `GraphShieldService` construction. | `retrieval.retriever.EvidenceRetriever` | not computed |
| `data/processed/cases/subgraphs/<CASE_ID>.parquet` | Materialized investigation graph for a case. | Optional per case. Required only when the graph endpoint/view is expected to show a materialized graph for that case. | `services.case_graph_service.CaseGraphService` | not computed |
| `models/lightgbm_graph_v1.joblib` | Frozen graph LightGBM model used by Phase 11 explainability; also part of strict readiness. | Required for explainability and strict readiness. | `explainability.explanation_service.Phase11ExplanationService`; `enterprise.phase14_runtime.DEFAULT_REQUIRED_PATHS` | not computed |
| `models/probability_calibrator_graph_v1.joblib` | Frozen calibration bundle and feature schema for the graph model; also part of strict readiness. | Required for explainability and strict readiness. | `explainability.explanation_service.Phase11ExplanationService`; `enterprise.phase14_runtime.DEFAULT_REQUIRED_PATHS` | not computed |
| `models/v2/phase10_fusion_calibrator_v1.joblib` | Frozen Phase 10 fusion calibration bundle. | Required for strict readiness; optional for basic graph-only explanation because the explainability service checks for its existence before loading it. | `enterprise.phase14_runtime.DEFAULT_REQUIRED_PATHS`, `explainability.explanation_service.Phase11ExplanationService` | not computed |
| `data/processed/gold/model_features_v2_graph_split.parquet` | Frozen point-in-time feature rows used to reconstruct model inputs and explanation evidence. | Required for Phase 11 explainability. | `explainability.explanation_service.Phase11ExplanationService` and dependent reason/graph/temporal explanation services | not computed |
| `data/processed/modeling/v2/phase10/locked_test_predictions_v1.parquet` | Frozen Phase 10 component/fusion scores used to expose the temporal and fusion context in explanations. | Optional. Explanations continue without this file, but TGN/fusion component context is absent. | `explainability.explanation_service.Phase11ExplanationService` | not computed |
| `data/policy/processed/policy_corpus.parquet` | Processed policy corpus used for cited policy retrieval. | Required only when policy-grounded search is exercised. | `retrieval.policy_retriever.PolicyRetriever` | not computed |
| `data/policy/indexes/policy_tfidf_index.joblib` | Lexical retrieval index for policy search. | Required only when policy-grounded search is exercised. | `retrieval.policy_retriever.PolicyRetriever` | not computed |
| `data/policy/indexes/policy_dense_embeddings.npy` | Dense embedding matrix for hybrid policy retrieval. | Required only when policy-grounded search is exercised. | `retrieval.policy_retriever.PolicyRetriever` | not computed |
| `data/policy/indexes/policy_index_metadata.parquet` | Retrieval metadata aligned to the processed policy corpus. | Required only when policy-grounded search is exercised. | `retrieval.policy_retriever.PolicyRetriever` | not computed |
| `data/policy/indexes/policy_index_manifest.json` | Policy-index manifest used to validate corpus integrity/alignment. | Required only when policy-grounded search is exercised. | `retrieval.policy_retriever.PolicyRetriever` | not computed |

### Tracked readiness evidence

The default strict readiness contract also checks:

- `reports/v2/phase13/phase13_final_certification_v1_report.json`

That file is Git-tracked, so it belongs to section A rather than the out-of-band handoff.

Phase 11 explainability also reads:

- `reports/v2/phase10/phase10_certification_v1.json`

That file is also Git-tracked.

### Policy model cache note

`PolicyRetriever` instantiates the Sentence Transformers models `sentence-transformers/all-MiniLM-L6-v2` and, when reranking is enabled, `cross-encoder/ms-marco-MiniLM-L-6-v2`. Those model downloads/caches are external dependency assets, not GraphShield-generated artifact handoff files. An offline environment must provide an appropriate local Hugging Face cache separately.

## C. Mutable runtime state

The following state is intentionally separate from the immutable artifact handoff above:

- `data/phase7/analyst_workbench.sqlite`
  - Created/initialized by `services.analyst_state.AnalystStateService`.
  - Stores analyst review state and append-only audit events.
  - Mutable runtime state.
  - Not part of reproducible setup and should not be restored as if it were an immutable model/data artifact.

- `data/processed/cases/case_store.duckdb`
  - Generated/used by investigation build and retrieval workflows.
  - Mutable/generated local case-store state.
  - Not part of the minimum reproducible analyst setup and should not be restored as authoritative runtime state.

For a fresh developer/demo setup, these databases should be generated by the relevant runtime/pipeline workflow when needed rather than treated as frozen handoff inputs.

## D. CI-only fixtures

`scripts/ci/prepare_ci_test_artifacts.py` generates deterministic artifacts for repository tests when `GITHUB_ACTIONS=true`.

Its outputs include test versions of:

- `data/processed/cases/case_queue.parquet`
- `data/processed/cases/evidence_documents.parquet`
- `data/processed/cases/evidence_tfidf_index.joblib`
- a deterministic materialized case subgraph
- `data/processed/gold/model_features_v2_graph_split.parquet`
- `data/processed/modeling/v2/phase10/locked_test_predictions_v1.parquet`
- `models/lightgbm_graph_v1.joblib`
- `models/probability_calibrator_graph_v1.joblib`

These outputs are **TEST-ONLY**.

They exist to make the automated test suite deterministic in a clean checkout. They are not production model substitutes, are not real GraphShield runtime artifacts, and must not be presented as certified model/data handoff files for the analyst demo.

The clean-check verification for the CPU/demo/API/test contract completed with:

- Python 3.12.14
- installation from `requirements-repro.lock.txt`
- `83 passed` in a disposable fresh checkout

That result validates the repository test contract; it does not replace the real out-of-band artifacts listed in section B.
