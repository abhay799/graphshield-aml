# GraphShield AML — Phase 5 Temporal Graph Learning

## Objective

Measure whether learned temporal graph state adds value beyond transaction-level and handcrafted point-in-time graph features.

## Validation Comparison

| Model | Average Precision | Recall@1% | Recall@5% | Precision@1% |
|---|---:|---:|---:|---:|
| Transaction LightGBM | 0.000197 | 0.0000 | 0.0000 | 0.000000 |
| Transaction + Graph LightGBM | 0.022286 | 0.3333 | 0.3333 | 0.003175 |
| TGN | 0.004555 | 0.3333 | 0.6667 | 0.003175 |
| Graph + TGN Hybrid | 0.029219 | 0.6667 | 0.6667 | 0.006349 |

## Test Comparison

| Model | Average Precision | Recall@1% | Recall@5% | Precision@1% |
|---|---:|---:|---:|---:|
| Transaction LightGBM | 0.007056 | 0.0303 | 0.4848 | 0.002674 |
| Transaction + Graph LightGBM | 0.000883 | 0.0000 | 0.0909 | 0.000000 |
| TGN | 0.004597 | 0.0606 | 0.3333 | 0.005348 |
| Graph + TGN Hybrid | 0.000745 | 0.0000 | 0.0606 | 0.000000 |

## Validation-Selected Champion

**Graph + TGN Hybrid**

The champion is selected using validation Average Precision, with Recall@Top1% as the secondary criterion.

## TGN Leakage Policy

All transactions sharing the same timestamp are scored from the same pre-timestamp graph state. The group enters TGN memory only after all predictions for that timestamp are made.

## Hybrid

The hybrid combines handcrafted graph-model and TGN rankings using a fusion weight chosen only on validation data.

## Interpretation

If TGN or the hybrid does not beat the handcrafted graph model, that is still a valid result: the engineered graph signals may already capture most of the useful temporal structure in this synthetic dataset.