# GraphShield AML Technical Demo Script (4–6 minutes)

This script is designed to be used with the actual running Streamlit command center and the repository-backed deterministic demo scenario. It should be recorded from the real application, not from a fabricated mockup.

## Target audience

- recruiters
- engineering managers
- technical reviewers
- portfolio evaluators

## Recording objective

Explain GraphShield as a graph-native AML investigation-support prototype with real repository implementation, evidence provenance, and a human-controlled review workflow.

## Script structure

### 0:00–0:25 — Opening

Narration:

> GraphShield AML is a graph-native investigation-support system for AML review. It connects transaction alerts, graph context, case evidence, policy retrieval, and explanation into a single human-controlled workflow. The data in this repository is synthetic and the system is designed for research and portfolio review, not autonomous enforcement.

On screen:
- portfolio hero or Streamlit entry page
- visible provenance and human-review language

### 0:25–0:55 — Problem framing

Narration:

> A single transaction score is not enough for investigation. AML review needs context: counterparty history, network structure, recent behavior, path evidence, policy context, and explainability. GraphShield puts those pieces together for the analyst instead of forcing a blind single-point decision.

On screen:
- mission control or queue view
- a few ranked alerts

### 0:55–1:35 — Architecture overview

Narration:

> The system starts with transactions and canonical data. That flows into point-in-time features, rules and ML, temporal and graph intelligence, and then into case queueing, evidence bundles, and model explanation. The final layer is human review, audit, and governance.

Visual flow to show:
- Transactions
- canonical data
- point-in-time features
- ML / graph / TGN
- case queue
- graph evidence
- policy retrieval
- human review

Use the static portfolio page or architecture slides if they help structure the explanation.

### 1:35–2:35 — Mission Control and risk queue

Narration:

> Here is the AML Mission Control view. It gives the analyst a prioritized queue, source provenance, and a clear read-only working model. The system ranks and organizes the queue, but it does not act on behalf of the bank or outside the investigator’s review.

On screen:
- AML Mission Control page
- Risk / Alert Intelligence page
- top risk cases visible

### 2:35–3:25 — Case investigation and graph explorer

Narration:

> We open a deterministic demo case and move into graph evidence. The graph view shows the core account and counterparty relationships around the focal event. This is point-in-time evidence for review, not proof of criminal conduct.

On screen:
- Case Investigation page
- Graph Explorer
- one case with connected account path or suspicious graph context

### 3:25–4:05 — Evidence, explanation, and policy retrieval

Narration:

> The investigation flow includes path evidence, explanation, and policy retrieval. The system surfaces citation-backed policy context and grounded review notes, while keeping the final decision in the human investigator’s hands.

On screen:
- policy evidence cards
- explanation panel
- one or two citations or retrieved evidence items

### 4:05–4:40 — Provenance and governance boundary

Narration:

> Provenance is explicit. The repository separates measured evidence, historical certification, synthetic data, static demo outputs, and not-proven-live claims. That matters because we are showing evidence-backed research support, not a live production AML system or a regulatory filing engine.

On screen:
- Provenance / Audit page
- Governance or status view

### 4:40–5:00 — Closing

Narration:

> GraphShield demonstrates a complete end-to-end workflow: data engineering, graph intelligence, model explanation, policy support, bounded investigation assistance, and governance in one human-controlled AML review system. The real strength is the disciplined boundary between evidence and action.

Close on:
- static portfolio page or final status view
- no unsupported production claim

## Important wording constraints

Use language like:
- investigation support
- risk signal
- network context
- evidence-backed
- human review required
- research/portfolio system

Avoid:
- production-ready
- regulatory certification
- guaranteed detection
- autonomous SAR/STR filing
- automatic account blocking
- criminal conclusion
- live deployment claim

## Suggested demo case

Use deterministic scenario `GS-AML-002` as the primary case if the path view is available and visually rich.

Fallback: `GS-AML-001` if the queue and triage view need to be emphasized first.
