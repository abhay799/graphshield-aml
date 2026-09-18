# Validation

## Interpretation

GraphShield contains several forms of validation evidence. They answer different questions and must not be collapsed into a claim that the current checkout was freshly certified or deployed.

| Evidence | What it supports | What it does not support |
|---|---|---|
| Source modules and configuration | A capability is implemented in the repository | A dependency or service is currently available |
| Unit/integration tests | Specific contract behavior when tests are run with required artifacts | Production behavior or real-world detection quality |
| Validation scripts and reports | Historical data/model/integration checks | A rerun in the current environment |
| Certification manifests/reports | Historical phase-gate outcomes and artifact references | Regulatory certification or a live production release |
| Docker/Kubernetes manifests | Deployment/readiness contract implementation | A running cluster, cloud network, or achieved SLO |

## Test inventory

The repository contains 34 `tests/test_*.py` files and 83 test functions. Coverage is strongest for Phase 7 service contracts and Phases 11–15: explainability, bounded-agent grounding/audit behavior, governance, deployment/integrity contracts, recovery, and release gates.

The GitHub Actions workflow compiles selected source files, validates Compose syntax, and performs basic repository checks. It does not run the full pytest suite. Its configured branch triggers are `master` and `main`, whereas the recovered active branch is `graphshield-v2`; this is a current CI coverage limitation.

## Historical certification artifacts

Committed evidence includes:

- `reports/final/phases_1_6_certification.md`
- `reports/final/phase7_certification.md`
- `reports/final/phase8_certification.md`
- `reports/v2/phase10/phase10_certification_v1.json`
- Phase 11–15 reports under `reports/v2/phase11` through `reports/v2/phase15`

The Phase 15 final report records successful prior gates and explicitly states that it does not claim production SLO attainment or external-cloud smoke validation. Its stored smoke report is in-process and read-only.

## Model-validation record

The repository stores metrics, prediction artifacts, calibration reports, and manifests for several model generations. Avoid treating legacy reports as one current champion declaration:

- An earlier selection report names CatBoost.
- The Phase 5 unified manifest identifies `lightgbm_graph` for its scope.
- The Phase 10 certification records a frozen `graph_tgn_fusion` candidate.

Model conclusions must be read with their phase, split, artifact, and selection constraints. Historical reports are not a claim of present operational performance or guaranteed detection efficacy.

## How to validate a future change

Validation should be proportional to the changed area and performed only in an environment where writing runtime state is authorized. At minimum:

1. Check documentation links and referenced paths for documentation-only changes.
2. Run affected tests without altering certified artifacts.
3. Run the relevant phase validation/certification gate when changing its implementation or artifact contract.
4. Record the command, environment, artifact availability, and results separately from historical certification evidence.

See [Limitations](LIMITATIONS.md) for data/model artifact and environment constraints.
