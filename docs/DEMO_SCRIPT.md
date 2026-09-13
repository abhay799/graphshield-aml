# GraphShield AML — 3-Minute Demo Script

## 0:00–0:20 — Problem

“AML monitoring can generate more alerts than an investigator can review deeply. GraphShield prioritizes those alerts and organizes the evidence needed for a human investigation.”

## 0:20–0:40 — Command Center

Open **Command Center**.

Show:
- backend is live
- real case source is available
- integration status for explainability, agentic investigation, governance, and integrity

Say:

“GraphShield is not just a classifier. It connects the risk model to an analyst workflow.”

## 0:40–1:00 — Case Queue

Open **Case Queue** and choose a high-ranked case.

Say:

“The queue is ranked so limited analyst capacity is spent on the highest-priority cases first.”

## 1:00–1:30 — Investigation + Graph

Open **Investigation**, then **Graph Explorer**.

Show:
- risk/case context
- materialized point-in-time network
- focal transaction
- graph metadata

Say:

“The graph is built point-in-time, so I avoid using future relationships as evidence for an earlier event.”

## 1:30–1:55 — Explainability

Open **Explainability**.

Say:

“I deliberately separate TreeSHAP model attribution from deterministic reason codes and graph/temporal evidence. The TGN context is not falsely presented as SHAP.”

## 1:55–2:25 — AI Investigator + Policy RAG

Open **AI Investigator**.

Ask:

> Why is this case prioritized, what supporting and countervailing evidence exists, and what policy context should the analyst review?

Then show **Policy RAG**.

Say:

“The agent can only call allowlisted read-only tools. Important claims must be grounded in retrieved case or policy evidence. It cannot block an account, close a case, or file a regulatory report.”

## 2:25–2:45 — Governance

Open **Governance**.

Say:

“Drift does not automatically retrain the model. Feedback must be adjudicated, and any retraining proposal stays human-gated.”

## 2:45–3:00 — Reliability

Open **Deployment**.

Say:

“The final phases add deployment readiness, artifact integrity, recovery verification, and release gates. These demonstrate engineering readiness, not a claim of live-bank production SLOs.”

## Closing sentence

“GraphShield turns risk into evidence so a human can investigate, explain, and audit the decision.”
