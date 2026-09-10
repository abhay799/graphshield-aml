# GraphShield AML — Phase 3 Modeling Report

## Modeling Objective

Prioritize transactions for analyst review using point-in-time AML risk features.

The system is an investigation prioritization prototype using public/synthetic data and is not a production AML compliance decision system.

## Final Model Selection

Champion: **catboost**

Selection was performed using validation data.

Primary metric: Average Precision.

Secondary metric: Recall@Top1%.

## Validation Candidates

| Model | AP | Recall@1% | Recall@5% | Precision@1% |
|---|---:|---:|---:|---:|
| logistic | 0.000135 | 0.0000 | 0.0000 | 0.000000 |
| lightgbm | 0.000197 | 0.0000 | 0.0000 | 0.000000 |
| catboost | 0.018949 | 0.3333 | 1.0000 | 0.003175 |

## Final Test Performance

- Average Precision: 0.004322
- ROC-AUC: 0.899807
- Recall@Top1%: 0.0000
- Recall@Top5%: 0.2121
- Recall@Top10%: 0.5152
- Brier Score: 0.00088290
- ECE: 0.00066867

## Rules vs ML

| Capacity | Rule Recall | ML Recall | Rule Precision | ML Precision |
|---|---:|---:|---:|---:|
| top_1pct | 0.0000 | 0.0000 | 0.000000 | 0.000000 |
| top_5pct | 0.0000 | 0.2121 | 0.000000 | 0.003745 |
| top_10pct | 0.0000 | 0.5152 | 0.000000 | 0.004548 |

## Explainability

TreeSHAP explanations are generated for global feature importance and high-risk transaction-level explanations.

## Next Phase

Phase 4 will introduce graph-native account and transaction features to capture relationships that transaction-level tabular models may miss.