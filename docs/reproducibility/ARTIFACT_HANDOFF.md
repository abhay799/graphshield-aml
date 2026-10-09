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

### Railway deployment bundle reproducibility

The successful Railway live-scoring deployment was built from a bounded local deployment bundle, not directly from GitHub alone. The Dockerfile used by that bundle is preserved at `deploy/railway/Dockerfile`.

That bundle includes runtime inputs under `models/`, `data/`, and `reports/` that are intentionally outside the normal Git checkout or may be Git-ignored. Therefore, the deployed Railway image cannot be reproduced from the GitHub repository alone. Rebuilding it requires the corresponding out-of-band artifacts described in this handoff document. Those artifacts must remain external; copying the deployment Dockerfile into Git does not make the model/data/report artifacts part of source control.

### Manual Railway releases

GitHub auto-deploy is disabled for `graphshield-api`: its source repository is null. Documentation and UI pushes do not start builds. Releases are manual bounded-bundle uploads through the Railway CLI, using `deploy/railway/Dockerfile` as the bundle's root `Dockerfile`. The repository root Dockerfile is a separate build.

Release procedure (PowerShell, from the repository root):

1. Commit and push the reviewed release; record `git rev-parse HEAD`. Prepare a vetted, bounded artifact directory containing the required `models/`, `data/`, and `reports/` inputs listed below. Do not use CI fixtures or the entire working data tree.
2. Set the artifact path and create a fresh HEAD bundle. Overlay external artifacts, then re-extract tracked files so HEAD remains authoritative:

```powershell
$releaseArtifacts = 'C:/path/to/verified-bounded-artifacts'
$releaseSha = git rev-parse HEAD
$releaseBundle = Join-Path (Get-Location) "tmp/railway-release-$releaseSha"
$releaseArchive = Join-Path (Get-Location) "tmp/railway-release-$releaseSha.zip"
git archive --format=zip --output=$releaseArchive HEAD src reports models data/processed/cases requirements-core.txt requirements-ml.txt requirements-live-scoring.txt deploy/railway/Dockerfile
if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
New-Item -ItemType Directory -Path $releaseBundle -ErrorAction Stop | Out-Null
Expand-Archive -LiteralPath $releaseArchive -DestinationPath $releaseBundle
foreach ($artifactRoot in @('models', 'data', 'reports')) {
    Copy-Item -LiteralPath (Join-Path $releaseArtifacts $artifactRoot) -Destination $releaseBundle -Recurse -Force
}
Expand-Archive -LiteralPath $releaseArchive -DestinationPath $releaseBundle -Force
Copy-Item -LiteralPath (Join-Path $releaseBundle 'deploy/railway/Dockerfile') -Destination (Join-Path $releaseBundle 'Dockerfile')
@'
from pathlib import Path
import sys
bundle = Path(sys.argv[1])
(bundle / '.dockerignore').write_text('__pycache__\n*.pyc\n*.log\n', encoding='utf-8')
(bundle / 'run_api.py').write_text('import os\nimport uvicorn\nuvicorn.run("api.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))\n', encoding='utf-8')
'@ | python - $releaseBundle
```

3. Review the bundle manifest and artifact hashes; exclude credentials, mutable databases, test fixtures, and unrelated datasets. If Docker Hub returns 429, select the official ECR mirror in the generated bundle only:

```powershell
@'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / 'Dockerfile'
p.write_text(p.read_text(encoding='utf-8').replace('ARG BASE_IMAGE=python:3.12-slim', 'ARG BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim'), encoding='utf-8')
'@ | python - $releaseBundle
```

For a local Docker build, use `docker build --build-arg BASE_IMAGE=public.ecr.aws/docker/library/python:3.12-slim -t graphshield-release $releaseBundle`. The override leaves application COPY instructions and artifact payloads unchanged; it does not promise identical complete image digests or dependency-install layers across registries or later rebuilds.

4. Upload explicitly to the existing service. `--no-gitignore` is required so ignored runtime binaries are included:

```powershell
railway.cmd up $releaseBundle --path-as-root --no-gitignore --project f9a59c1b-62ab-4f63-a7e7-794d5a20c973 --service graphshield-api --environment production --detach --message "HEAD $releaseSha manual bounded bundle"
railway.cmd deployment list --service graphshield-api --environment production --json
```

5. Wait for the returned deployment ID to reach `SUCCESS`; inspect build/runtime logs if it fails. Confirm that the active deployment is that ID and GitHub remains disconnected. Run public health, future-time/no-commit, valid/duplicate, oversized-body, rate-limit (with and without spoofing), and browser-origin CORS checks with unique synthetic IDs and current timestamps. Leave at least 60 seconds between bursts. Record the commit, deployment ID, manifest hashes, and results.

### Railway client-IP trust boundary

Client-IP resolution uses the leftmost `X-Forwarded-For` value, then `X-Real-IP`, then the connection peer. The verified Railway edge replaces caller-supplied forwarding headers: the resolved IP matched the caller's public egress IP, while the connection peer was a shared `100.64.0.x` proxy. This depends on Railway's edge replacing `X-Forwarded-For`. Re-test received headers, real-IP resolution, and rotating-header rate-limit bypass attempts whenever the proxy chain, edge configuration, or hosting platform changes. Remove temporary debug views after verification.

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
