# GraphShield AML - Global Statistical & Leakage Audit

- Locked test rows: 761,639
- Locked test positives: 1,561
- Champion: lightgbm_graph
- Champion selected on validation only: PASS
- Test used for champion selection: False
- PIT/leakage validation: PASS
- Entity/account overlap audit: PASS
- Graph model dataset validation: PASS
- Connected-component feature isolation: PASS

## Locked Test

- Baseline AP: 0.00167376
- Graph AP: 0.05452114
- AP improvement: 0.05284738
- Baseline Recall@1%: 0.01409353
- Graph Recall@1%: 0.46060218
- Recall@1% improvement: 0.44650865

## Paired Bootstrap 95% CIs

- Graph AP: [0.04903263, 0.05881437]
- Graph - Baseline AP: [0.04744661, 0.05711178]
- Graph Recall@1%: [0.40938286, 0.45326887]
- Graph - Baseline Recall@1%: [0.39484042, 0.43844677]