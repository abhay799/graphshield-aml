# GraphShield AML — Internal Release Certification

Status: PASS for the internal research-only release gate

## Scope and claim

This certification covers the current repository state for GraphShield AML as a local, evidence-backed, human-review-first investigation-support project. It is not a production deployment certification, not a live AML compliance approval, and not a regulatory or supervisory attestation.

The repository remains scoped to local evidence, deterministic demo scenarios, and repository-backed workflow packaging. The system is positioned as decision support for analyst review, not autonomous enforcement or external operational control.

## Fresh evidence reviewed

The following checks were run against the repo’s actual project environment and local artifacts:

- Branch: `graphshield-v2`
- HEAD: `347c265f0c4000836a01e457939311c43efaed4d`
- Python environment: project virtual environment (`.venv\Scripts\python.exe`)
- Compile validation: `python -m compileall -q src tests` completed successfully
- Test suite: `./.venv/Scripts/python.exe -m pytest -q` completed successfully
  - Result: `83 passed` in `245.17s` (about `4:05`)
- Deterministic scenario suite: `scripts/demo/run_scenarios.py --scenario all`
  - Result: `4/4` passed (`GS-AML-001` through `GS-AML-004`)
- FastAPI health endpoint: `http://127.0.0.1:8000/health`
  - Result: `HTTP 200`
  - Response: `{"status":"ok","service":"GraphShield AML","mode":"read_only","case_queue_rows":7617,"champion":"lightgbm_graph","phase_1_6_artifacts":"frozen"}`
- Streamlit app: `http://127.0.0.1:8505/`
  - Result: `HTTP 200`
- Static portfolio: `http://127.0.0.1:8008/`
  - Result: `HTTP 200`
- Evidence manifest: `docs/evidence/EVIDENCE_MANIFEST.json`
  - Result: `16 evidence entries`, `0 missing repository-relative paths`
- Repo hygiene: `git diff --check` ran clean in the reviewed release scope

## Issue classification

A. RELEASE BLOCKING
- None identified in the review scope.

B. NON-BLOCKING LIMITATION
- Synthetic/local-only evidence; not live-bank production data.
- No production deployment or external regulatory result claimed.
- Runtime is intentionally local and analyst review oriented.
- Static portfolio and demo assets are presentation-only, not live-service proof.

C. FUTURE INFRASTRUCTURE INTEGRATION
- Optional cloud, GPU, and integration work remains outside the current release claim.
- Broader production monitoring, SLO validation, and external system integration should be treated as future work.

## Evidence classification

This repo remains aligned with the documented evidence taxonomy:

- MEASURED: local repo validation, compile checks, test suite, scenario runs
- HISTORICAL CERTIFICATION: retained historical reports and prior milestone evidence
- SYNTHETIC: IBM AML LI-Small synthetic data context used for local workflow validation
- SIMULATED: deterministic local scenarios and artifact-backed demo cases
- STATIC DEMO: static portfolio + demo packaging for reviewer presentation
- READINESS TARGET: future live deployment and broader operational integration remain explicit targets, not claims
- NOT MEASURED: live production metrics, external regulatory validation, and real-world deployment monitoring
- NOT PROVEN LIVE: no claim of live monitoring, real-time production operations, or external compliance certification

## Operational boundaries

The project is currently valid as a local, read-only, analyst-facing investigation-support package with these boundaries:

- Human review remains required before operational action
- Models and graph workflows are used for decision support, not autonomous enforcement
- Local artifacts are repository-backed and deterministic for demo and review conditions
- No external production or compliance claim is made in this certification
- Any broader deployment, model governance, or operational rollout would require separate review outside this internal release gate

## Recommended release identifier

`v0.9.0-research`

This identifier is justified because the project is internally validated and reviewer-safe, but it remains a research and portfolio-facing release rather than a production deployment release.

## Final release decision

FINAL DECISION: `INTERNAL RESEARCH RELEASE — PASS`

This repository passes the current internal productization gate for honest, reviewer-oriented packaging and evidence-backed validation within the project’s stated scope.

This is an internal research certification only. It does not certify production readiness, live operations, external regulatory compliance, or third-party deployment approval.
