# GraphShield AML

Graph-native AML transaction monitoring and evidence-grounded analyst investigation platform built using public and synthetic financial data.

> Decision-support system only. GraphShield does not autonomously block accounts, close cases, or submit regulatory filings.

## Overview

GraphShield combines point-in-time feature engineering, graph intelligence, machine learning, policy retrieval, case investigation, and an analyst workbench into one end-to-end AML research platform.

`	ext
Transactions
    |
    v
Canonical + PIT-safe features
    |
    v
Rules + ML + Graph Intelligence
    |
    v
Risk-ranked Case Queue
    |
    +--> Transaction Graphs
    +--> Paths and History
    +--> Evidence Retrieval
    +--> Regulatory Policy RAG
    +--> Analyst Review State
    |
    v
Human Investigation Decision Support
`",
",


- 5,078,345 transactions processed
- 5,177 positive transactions
- 515,088 graph account nodes
- Chronological train / validation / test split
- 761,639 transactions in the locked test split
- 7,617 cases in the authoritative analyst queue
- Top 374 cases eagerly materialized
- 693 authoritative policy chunks indexed

## Machine Learning

Models investigated include:
- Rule-based baseline
- Logistic / classical baseline modeling
- LightGBM and CatBoost
- Graph-derived LightGBM
- Temporal Graph Network research candidate
- Graph + temporal fusion experiment

### Frozen Champion

**Model:** lightgbm_graph

The champion was selected using validation performance only. The test split was not used for model selection.

| Metric | Baseline | Graph Champion |
|---|---:|---:|
| Average Precision | 0.00167376 | 0.05452114 |
| Recall@1% | 0.01409353 | 0.46060218 |

Paired bootstrap 95% confidence intervals:

- Graph AP: [0.04903263, 0.05881437]
- Graph - Baseline AP improvement: [0.04744661, 0.05711178]
- Graph Recall@1%: [0.40938286, 0.45326887]
- Graph - Baseline Recall@1% improvement: [0.39484042, 0.43844677]

## Leakage and Point-in-Time Controls

- Chronological train / validation / test splits
- Strict prior-time historical features
- Point-in-time graph feature construction
- Account/entity overlap audit
- Pair overlap audit
- Feature leakage validation
- Test split isolated from model selection

## Training Disclosure

Tree-model training used a deterministic 25% hash sample of the training split because of local compute constraints. Validation and test evaluation used the full corresponding splits.

## Temporal Graph Research

- TGN training used a 250,000-event chronological prefix
- Training used 1 epoch on CPU
- TGN is retained as a research / ablation component
- It is not presented as a production-quality full-dataset TGN

## Evidence-Grounded Investigation

For high-risk cases, GraphShield provides:
- Case overview
- Transaction history
- Counterparty evidence
- Transaction paths
- Interactive graph investigation
- Searchable case evidence
- Unified case intelligence snapshot

## Regulatory and Policy RAG

The policy retrieval pipeline uses authoritative AML/CFT documents with provenance metadata.

Retrieval combines:
- TF-IDF lexical retrieval
- MiniLM dense retrieval
- Reciprocal-rank fusion
- Optional cross-encoder reranking
- Grounded evidence with citation validation

Evaluation:
- Case Hit@5: 1.0000
- Case MRR: 0.8125
- Policy Hit@5: 1.0000
- Policy MRR: 1.0000

LLM generation is optional. Retrieval and investigation remain usable when no external LLM API key is configured.

## Analyst Workbench

Phase 7 integrates the intelligence pipeline into an analyst-facing system.

Features include:
- Prioritized case queue
- Case investigation workspace
- Interactive transaction graph
- Evidence search
- Policy search
- Unified case intelligence
- Analyst review status
- Analyst notes
- Append-only audit history
- Human-review governance controls

Analyst operational state is stored separately from the frozen intelligence artifacts.

## Product Layer

Backend:
- FastAPI
- Pydantic request validation
- Read-only intelligence services
- Separate mutable analyst-state service
- Health endpoint
- Prometheus metrics endpoint
- Structured JSON request logging
- Request IDs
- HTTP latency metrics

Frontend:
- Streamlit analyst workbench
- PyVis graph visualization

## Docker Architecture

GraphShield runs as two services:

`	ext
Browser
   |
   v
Streamlit Workbench :8501
   |
   v
FastAPI :8000
   |
   +--> AML artifacts (read-only)
   +--> Policy corpus (read-only)
   +--> Analyst SQLite state (writable)
`",
",


- API bound to localhost for local demo use
- Trusted-host validation
- Security response headers
- .env excluded from Git
- .env.example contains no credentials
- API keys loaded from environment variables
- Frozen intelligence artifacts mounted read-only
- Human review required
- No autonomous account blocking
- No autonomous case closure
- No autonomous regulatory filing

## Observability

- Structured JSON HTTP logs
- Request correlation IDs
- HTTP request counters
- HTTP latency histograms
- Prometheus-compatible /metrics endpoint
- Docker health checks

## Automated Validation

Local regression suite:

16 tests passed

A GitHub Actions workflow is included for source syntax, repository safety, and Docker Compose validation. Remote GitHub execution is not claimed until the repository is pushed and the workflow runs there.

## Quick Demo

Start:
powershell -ExecutionPolicy Bypass -File scripts\demo\start.ps1

Status:
powershell -ExecutionPolicy Bypass -File scripts\demo\status.ps1

Stop:
powershell -ExecutionPolicy Bypass -File scripts\demo\stop.ps1

Local endpoints:
- Workbench: http://127.0.0.1:8501
- API: http://127.0.0.1:8000
- API Docs: http://127.0.0.1:8000/docs
- Metrics: http://127.0.0.1:8000/metrics

## Technology Stack

Data: Python, Polars, Pandas, DuckDB, PyArrow
Machine Learning: scikit-learn, LightGBM, CatBoost
Graph: transaction graphs, graph-derived features, temporal graph research
Retrieval: SentenceTransformers, TF-IDF, dense retrieval, reranking, grounded RAG
Backend: FastAPI, Pydantic
Frontend: Streamlit, PyVis
Operations: Docker, Docker Compose, Prometheus metrics, GitHub Actions

## Responsible-Use Scope

GraphShield AML is a portfolio and research investigation system built using public and synthetic data.

It is designed for analyst prioritization and investigation support. Model scores and retrieved policy evidence require qualified human review before operational or regulatory action.

## Project Status

- Phases 1-6 intelligence pipeline: CERTIFIED
- Phase 7 analyst integration: CERTIFIED
- Phase 8 productization: final audit in progress

---

Author: Abhay Kumar
