# GraphShield AML — Benchmark and Evidence Summary

This document is an honest evidence package for what the repository proves and what it does not prove. It is intentionally not a live-production claim, regulatory statement, or an apples-to-apples leaderboard.

## Evidence taxonomy

The repository contains multiple provenance classes, and they must remain separate:

- MEASURED: numeric evidence recorded in repo artifacts
- HISTORICAL CERTIFICATION: prior phase artifacts that record pass/fail status in repository history
- SYNTHETIC: IBM AML LI-Small synthetic data, not real-bank data
- SIMULATED: smoke/replay or readiness exercises, not live traffic
- STATIC DEMO: deterministic scenario output produced for analyst demonstration
- READINESS TARGET: release gate status that says a human approval gate exists, not live production SLO attainment
- NOT MEASURED: metric or environment fact not directly available in repo artifacts
- NOT PROVEN LIVE: no current evidence of a running production deployment or external operating environment

## 1. Data evidence

### 1.1 Synthetic IBM AML dataset

Evidence:
- `reports/phase1_data_quality_report.md`
- `docs/LIMITATIONS.md`
- `docs/VALIDATION.md`

What is documented:
- Source dataset: IBM AML LI-Small
- Synthetic dataset: Yes
- Raw rows: 5,078,345
- Silver rows: 5,078,345
- Laundering rows: 5,177
- Laundering rate: 0.101943%
- Row preservation PASS: raw and silver row counts match
- Timestamp quality PASS: no null timestamps
- Null critical feature checks PASS

Provenance classification: SYNTHETIC + MEASURED

Important boundary:
- This evidence supports repository data integrity and feature engineering feasibility for the synthetic benchmark only.
- It is not evidence of real-bank detection performance or real customer risk behavior.

### 1.2 Processed artifact evidence

Relevant artifacts:
- `data/processed/cases/case_queue.parquet`
- `data/processed/cases/case_paths.jsonl`
- `data/processed/cases/bundles/*.json`
- `data/processed/graph/*.parquet`
- `data/processed/explanations/`
- `data/processed/entities/`

What these artifacts support:
- case queue ordering and investigation prioritization
- point-in-time graph context
- case bundles and evidence documents
- graph intelligence and motif/community context

Provenance classification: MEASURED + LOCAL READ-ONLY ARTIFACT

### 1.3 Chronology and point-in-time handling

Evidence:
- `docs/architecture/PHASE_INDEX.md`
- `src/validation/validate_graph_model_dataset.py`
- `src/validation/validate_phase1.py`
- `src/temporal/train_tgn.py`
- `docs/LIMITATIONS.md`

What is documented:
- The graph and temporal models are built with point-in-time constraints and strict temporal rules.
- The repository explicitly distinguishes historical artifacts from fresh verification.
- The TGN leakage policy is documented: all transactions sharing a timestamp are scored using the same pre-timestamp graph state.

Provenance classification: MEASURED + HISTORICAL CERTIFICATION

## 2. Model evidence

This section intentionally does not collapse different model families into one fake leaderboard. Different model artifacts use different dataset slices, training fractions, and validation/test scopes.

### 2.1 Model lineage ambiguity

The repository contains historical model reports that were generated in different phases and different scopes. Two examples:
- `reports/modeling/logistic_metrics.json` shows logistic baseline selection and test metrics.
- `reports/modeling/catboost_validation.json` and `reports/modeling/champion_test_metrics.json` record a different champion lineage than the earlier logistic artifact.
- `reports/modeling/tgn_metrics.json` records TGN experiment metrics under a temporal-graph setup.
- `reports/phase5_temporal_graph_report.md` reports a hybrid Graph + TGN evaluation under a different comparison framework.

This means model-lineage is ambiguous if read as a single current champion. The honest interpretation is: historical artifacts document multiple experiments and selection decisions, not one universal current production model.

### 2.2 Measured model metrics that actually exist

#### Logistic Regression

Source: `reports/modeling/logistic_metrics.json`

- selected_model: `logistic_unweighted`
- validation rows: 761,749
- validation positives: 760
- validation prevalence: 0.0009977039681049794
- validation ROC AUC: 0.6409290315144608
- validation average precision: 0.012282205194266997
- validation PR AUC: 0.04673463173993003
- validation recall@top_1pct: 0.2578947368421053
- validation recall@top_5pct: 0.30657894736842106
- test rows: 761,639
- test positives: 1,561
- test ROC AUC: 0.6351398046526056
- test average precision: 0.014094178927337352

Provenance classification: MEASURED + SYNTHETIC

#### LightGBM

Source: `reports/modeling/lightgbm_validation.json`

- model: `lightgbm`
- rows: 761,749
- positives: 760
- prevalence: 0.0009977039681049794
- ROC AUC: 0.10446269245471493
- average precision: 0.0011209543568731835
- PR AUC: 0.0007069077206976403
- recall@top_1pct: 0.031578947368421054
- recall@top_5pct: 0.04736842105263158

Provenance classification: MEASURED + SYNTHETIC

#### CatBoost

Source: `reports/modeling/catboost_validation.json`

- model: `catboost`
- rows: 761,749
- positives: 760
- prevalence: 0.0009977039681049794
- ROC AUC: 0.9798591917194184
- average precision: 0.18417278761674397
- PR AUC: 0.18356844112476092
- recall@top_1pct: 0.7263157894736842
- recall@top_5pct: 0.8631578947368421

Other relevant artifact:
- `reports/modeling/champion_test_metrics.json`
- champion: `catboost`
- test ROC AUC: 0.8998073757090546
- test average precision: 0.004321723235894369
- test recall@top_5pct: 0.21212121212121213

Provenance classification: MEASURED + SYNTHETIC + HISTORICAL CERTIFICATION context

#### Graph LightGBM

Source: `reports/modeling/graph_ablation_metrics.json`

Validation graph model:
- ROC AUC: 0.5594732289511619
- average precision: 0.0228225805914592
- PR AUC: 0.26660032697683583
- recall@top_1pct: 0.4763157894736842
- recall@top_5pct: 0.5342105263157895

Test graph model:
- ROC AUC: 0.6327921436108587
- average precision: 0.05375112142569439
- PR AUC: 0.3216786925880853
- recall@top_1pct: 0.4766175528507367
- recall@top_5pct: 0.600896860986547

Provenance classification: MEASURED + SYNTHETIC

#### TGN

Source: `reports/modeling/tgn_metrics.json`

- model: `TGN`
- validation average precision: 0.0009407477022529927
- validation ROC AUC: 0.4784267612693205
- validation recall@top_1pct: 0.006578947368421052
- validation recall@top_5pct: 0.034210526315789476
- final test average precision: 0.0016109586602384986
- final test recall@top_1pct: 0.005765534913516977

Provenance classification: MEASURED + SYNTHETIC

#### Graph + TGN hybrid

Source: `reports/phase5_temporal_graph_report.md`

Validation comparison (historical experiment):
- Graph + TGN Hybrid average precision: 0.029219
- Graph + TGN Hybrid recall@top_1pct: 0.6667
- Graph + TGN Hybrid recall@top_5pct: 0.6667

Interpretation from report:
- the hybrid was selected using validation Average Precision
- the report explicitly states the model might not beat the handcrafted graph model, and that is still a valid result

Provenance classification: MEASURED + HISTORICAL CERTIFICATION + SYNTHETIC

### 2.3 What this proves

The repository proves that:
- several model families were implemented and historically evaluated on synthetic IBM AML data
- model quality varies substantially by feature design, split, and selection criteria
- the benchmark data is highly imbalanced and the top-percentile recall metrics matter more than raw AUC in this setting

The repository does not prove:
- a single model is currently the production champion in a live environment
- the system works on real bank data
- the system has been externally certified or deployed in a regulated setting

## 3. Graph intelligence evidence

### 3.1 Implemented graph evidence

Relevant artifacts:
- `data/processed/graph/account_risk_v1.parquet`
- `data/processed/graph/account_risk_propagation_v1.parquet`
- `data/processed/graph/account_motif_intelligence_v1.parquet`
- `data/processed/graph/suspicious_communities_v1.parquet`
- `data/processed/graph/transaction_edges.parquet`
- `reports/v2/phase9/*.json`

Implemented capabilities documented in repo:
- graph construction from transaction edges and account entities
- account-risk propagation
- suspicious communities and community membership
- motif intelligence and account-level motif summaries
- pass-through and two-node cycle heuristics
- subgraphs and case-path extraction
- path evidence for suspicious network traversal

Provenance classification: MEASURED + IMPLEMENTED

### 3.2 Quantitative benchmark status

If a quantitative benchmark does not exist in the repository, the status is:
- IMPLEMENTED / NOT BENCHMARKED

This applies to several graph “intelligence” artifacts where the repo contains implementation and artifact generation evidence but no fresh, apples-to-apples accuracy benchmark across all graph evidence modes.

## 4. Investigation evidence

### 4.1 Case queue and bundle evidence

Relevant artifacts:
- `data/processed/cases/case_queue.parquet`
- `data/processed/cases/bundles/*.json`
- `data/processed/cases/case_paths.jsonl`
- `data/processed/cases/evidence_documents.parquet`

Observed repository evidence:
- `docs/demo/scenario_run_output.json` shows 4 deterministic scenarios running successfully
- scenario IDs: `GS-AML-001` to `GS-AML-004`
- case queue: 7,617 rows in the processed queue
- top queued case: `CASE_IBM_LI_SMALL_4310302`
- specific reverse-prior case: `CASE_IBM_LI_SMALL_4417139` with `reverse_prior_path` and `closes_multi_hop_cycle=true`

Provenance classification: MEASURED + STATIC DEMO + LOCAL READ-ONLY ARTIFACT

### 4.2 Explainability and policy retrieval evidence

Relevant artifacts:
- `data/processed/explanations/`
- `reports/phase6_investigation_rag_report.md`
- `src/validation/phase12_final_certification.py`
- `reports/v2/phase12/phase12_certification_v1.json`

What is supported:
- grounded investigation, evidence retrieval, and policy-context support
- bounded read-only agent tooling
- fail-closed grounding/audit behavior

What is not supported:
- no legal conclusion, no automatic filing, no account-block decision, no autonomous case closure

Provenance classification: HISTORICAL CERTIFICATION + MEASURED

### 4.3 Human-review boundary

Evidence from repo:
- `src/validation/phase15_final_certification.py`
- `reports/v2/phase15/final_release_gate_v1_report.json`
- `docs/LIMITATIONS.md`

Key statements:
- `human_release_approval_required`: true
- `automatic_account_blocking`: false
- `automatic_case_closure`: false
- `automatic_regulatory_submission`: false
- `production_slo_attainment_claimed`: false
- `external_cloud_smoke_claimed`: false

This is read-only decision-support evidence, not a compliance or legal decision engine.

## 5. Test and certification evidence

### 5.1 Freshly executed during Step 5

This project step did not rerun expensive training or re-certify the full model stack. What is freshly executed in the repo state is the deterministic demo scenario runner, which produced:
- `docs/demo/scenario_run_output.json`
- scenario IDs `GS-AML-001` through `GS-AML-004`
- PASS status for each scenario

Provenance classification: STATIC DEMO + FRESHLY EXECUTED DURING STEP 5

### 5.2 Historical certification evidence

Stored certifications include:
- `reports/final/phases_1_6_certification.md`
- `reports/final/phase7_certification.md`
- `reports/final/phase8_certification.md`
- `reports/v2/phase10/phase10_certification_v1.json`
- `reports/v2/phase11/phase11_certification_v1.json`
- `reports/v2/phase12/phase12_certification_v1.json`
- `reports/v2/phase13/phase13_final_certification_v1_report.json`
- `reports/v2/phase14/phase14_final_certification_v1_report.json`
- `reports/v2/phase15/phase15_final_certification_v1_report.json`

These artifacts should be treated as historical evidence of repository certification state, not as a fresh live verification performed when this document is read.

The Phase 15 final release gate explicitly states:
- final release ready for human approval: true
- human release approval required: true
- automatic production release: false
- production SLO attainment claimed: false
- external cloud smoke claimed: false

Provenance classification: HISTORICAL CERTIFICATION + READINESS TARGET

### 5.3 Available test counts

Evidence:
- `docs/VALIDATION.md`

Observed repository statement:
- 34 `tests/test_*.py` files
- 83 test functions
- strongest coverage is for service contracts and Phases 11–15 governance, explainability, and release-gate behavior

This supports contract coverage, but does not claim full production validation or external deployment verification.

## Final interpretation

The repository currently supports an honest statement like this:

- GraphShield AML shows implemented capabilities, historical pass status, and deterministic demo evidence on a synthetic IBM AML dataset.
- The repository demonstrates a decision-support and review workflow grounded in read-only evidence, bounded policy retrieval, and human review gates.
- The repository does not prove live production behavior, regulatory compliance, or real-bank performance.

The strongest truthful summary is:
- the code and artifacts contain measured evidence for synthetic benchmark experiments and historical repository certification
- the release/readiness artifacts establish a human-controlled, not-autonomous, review gate
- the evidence does not support claims of live-bank deployment, real-world AML effectiveness, or external certification
