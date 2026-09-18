# GraphShield AML Demo Scenarios

This package is intentionally limited to the repository's existing GraphShield AML evidence artifacts and investigation flow. It does not introduce new alert logic, new detection rules, or any autonomous actioning. Every scenario is read-only and should be treated as an analyst-support workflow with human review required.

## Provenance and safety guardrails

- Primary source of record: `data/processed/cases/case_queue.parquet`
- Supporting evidence: `data/processed/cases/case_paths.jsonl`, `data/processed/cases/bundles/*.json`, `data/processed/graph/*.parquet`
- Provenance label used by the app: `LOCAL READ-ONLY ARTIFACT`
- Safety rule: no scenario implies guilt, account blocking, SAR/STR filing, or automatic closure
- Allowed behavior: review, explain, compare, and document evidence; never action on behalf of the bank

## Scenario IDs and deterministic anchors

### GS-AML-001 — Queue triage and analyst prioritization

- Case anchor: `CASE_IBM_LI_SMALL_4310302`
- Trigger: first row in the queue after sorting by `risk_rank`
- Data source: `data/processed/cases/case_queue.parquet`
- Expected checkpoint:
  - `risk_rank == 1`
  - `case_status == "OPEN"`
  - `review_capacity == 0.01`
  - a valid `transaction_id` and `from_account_key` / `to_account_key` pair exists

### GS-AML-002 — Graph evidence and reverse-prior path review

- Case anchor: `CASE_IBM_LI_SMALL_4417139`
- Trigger: `case_paths.jsonl` row with a non-null `reverse_prior_path`
- Data source: `data/processed/cases/case_paths.jsonl`
- Expected checkpoint:
  - `reverse_prior_path` is not `null`
  - `closes_multi_hop_cycle == true`
  - `supporting_edges_strictly_prior == true` for the same case in the path catalog, when present

### GS-AML-003 — Suspicious community / motif context

- Graph anchors: `suspicious_communities_v1.parquet` and `account_motif_intelligence_v1.parquet`
- Trigger: graph artifact presence and non-empty rows
- Data source: `data/processed/graph/*.parquet`
- Expected checkpoint:
  - both parquet files exist
  - both have row counts greater than zero
  - the workflow is explicit that this is context for analyst review, not a conviction

### GS-AML-004 — Human review gate from the case bundle

- Case anchor: `CASE_IBM_LI_SMALL_4310302`
- Trigger: bundle `data/processed/cases/bundles/CASE_IBM_LI_SMALL_4310302.json`
- Data source: repository case bundle
- Expected checkpoint:
  - `investigation_policy.decision == "analyst_review_required"`
  - `autonomous_account_block == false`
  - `autonomous_case_closure == false`
  - `ground_truth_exposed == false`

## Reproducible execution

Use the repo venv and the deterministic runner:

PowerShell:

```powershell
& ".\.venv\Scripts\python.exe" scripts/demo/run_scenarios.py --scenario all
```

Or from any Python environment containing the repo dependencies:

```bash
python scripts/demo/run_scenarios.py --scenario all
```

To list the available scenarios:

```bash
python scripts/demo/run_scenarios.py --list
```

The runner writes a reproducible output artifact to:

- `docs/demo/scenario_run_output.json`

## Reset and rerun flow

1. Confirm the repo artifacts are present under `data/processed/...`
2. Run the scenario runner again with the same command
3. If you want a clean reset, delete the generated `docs/demo/scenario_run_output.json` and rerun
4. Do not edit the underlying processed artifacts in place for demo work; keep the scenario data deterministic and repository-backed

## Expected result shape

The runner prints a concise summary and saves structured JSON with these sections:

- `provenance`
- `repo_root`
- `scenario_count`
- `scenarios[]`
- per-scenario `status`, `checkpoints`, and `expected`

This keeps the demo deterministic, auditable, and consistent with the repository's local-read-only provenance model.
