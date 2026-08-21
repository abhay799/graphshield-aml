# GraphShield AML - Phase 1 Data Quality Report

## Dataset

- Source: IBM AML LI-Small
- Synthetic dataset: Yes
- Raw rows: 5,078,345
- Silver rows: 5,078,345

## Row Preservation

PASS - Raw and Silver row counts match.

## Target Distribution

- Legitimate transactions: 5,073,168
- Laundering transactions: 5,177
- Laundering rate: 0.101943%

## Transaction IDs

- Rows: 5,078,345
- Unique transaction IDs: 5,078,345
- PASS - Transaction IDs are unique.

## Timestamp Quality

- Earliest transaction: 2022-09-01 00:00:00
- Latest transaction: 2022-09-18 16:18:00
- Null timestamps: 0

## Amount Quality

- Negative amount_paid: 0
- Negative amount_received: 0
- Zero amount_paid: 0
- Zero amount_received: 0

## Critical Nulls

- transaction_id: 0 [PASS]
- event_ts: 0 [PASS]
- from_bank: 0 [PASS]
- from_account: 0 [PASS]
- to_bank: 0 [PASS]
- to_account: 0 [PASS]
- amount_paid: 0 [PASS]
- payment_currency: 0 [PASS]
- is_laundering: 0 [PASS]

## Storage

- Raw CSV: 453.63 MB
- Silver Parquet: 112.96 MB
- Storage reduction: 75.10%

## Phase 1 Status

**PASS - Silver dataset is ready for Phase 2 feature engineering.**