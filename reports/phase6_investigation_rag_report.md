# GraphShield AML - Phase 6 Investigation & RAG

## Case Evidence Retrieval

- Benchmark queries: 40
- Hit@5: 1.0000
- Mean Reciprocal Rank: 0.8125

## Authoritative Policy Retrieval

- Benchmark queries: 6
- Hit@5: 1.0000
- Mean Reciprocal Rank: 1.0000

## Citation Validation

- Citation metrics are not available until successful LLM-generated interactions exist.

## Safety / Governance

- Ground-truth laundering labels are not exposed to the investigation assistant.
- Case claims must be grounded in retrieved case evidence.
- Policy claims must be grounded in retrieved authoritative policy chunks.
- Unknown case or policy citation IDs fail citation validation.
- Investigation tools are read-only and allowlisted.
- Account blocking, case closure, SAR/STR filing, and regulatory reporting remain human decisions.