# GraphShield AML - Phases 1-6 Certification

Freeze timestamp: 2026-09-09T11:00:05.764233+00:00

## Certification

- Phase 1 - Data foundation: CERTIFIED
- Phase 2 - Features and rules: CERTIFIED
- Phase 3 - Baseline ML: CERTIFIED
- Phase 4 - Graph intelligence: CERTIFIED
- Phase 5 - Temporal GNN / fusion: CERTIFIED
- Phase 6 - Investigation and RAG: CERTIFIED

## Authoritative Champion

- Model: lightgbm_graph
- Selected on validation only
- Selection metric: Average Precision
- Test used for selection: False
- Analyst queue capacity: 1%

## Training Disclosures

- Tree model training used a 25% deterministic hash sample of the training split.
- Validation and test evaluation use the complete locked splits.
- TGN training used a 250,000-event chronological training prefix with 1 epoch on CPU.
- TGN is retained as a temporal research/ablation component; the graph LightGBM is the authoritative champion.

## Investigation

- Authoritative analyst queue: 7,617 cases
- Queue capacity: 1%
- Eager materialization: top 374 cases
- Remaining queued cases are eligible for on-demand investigation.

## RAG

- Case Hit@5: 1.0000
- Case MRR: 0.8125
- Policy Hit@5: 1.0000
- Policy MRR: 1.0000
- Grounding citation validator: PASS
- Adversarial/read-only safety: PASS
- Live external LLM generation is not required for core certification.

## Governance

- Decision support only
- No autonomous account blocking
- No autonomous case closure
- No autonomous regulatory filing

## Reproducibility

- Critical artifacts hashed: 29
- Hash algorithm: SHA-256
- Environment snapshot: reports/final/environment_freeze.txt
- Machine-readable freeze manifest: reports/final/phases_1_6_artifact_freeze.json

## Status

**GLOBAL PHASES 1-6 CERTIFIED**