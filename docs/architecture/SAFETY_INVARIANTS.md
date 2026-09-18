# Safety Invariants

These invariants describe the documented system boundaries reflected in GraphShield source, tests, and certification artifacts. They are product constraints, not claims of regulatory certification.

For the visual authority and safeguards model, see [Safety Control Plane](SAFETY_CONTROL_PLANE.md).

## Human authority

1. A human investigator owns case review, disposition, and any external action.
2. GraphShield prioritizes and organizes evidence; it does not make a legally binding or compliance-final determination.
3. GraphShield must not autonomously block accounts, close cases, file SAR/STRs, submit regulatory reports, or execute enforcement actions.

## Evidence and explanation

1. Investigation evidence is point-in-time: later transactions or relationships must not be represented as evidence available at the focal event.
2. Explanation channels remain distinct: TreeSHAP is limited to the frozen graph LightGBM component; deterministic reason codes, graph evidence, and TGN context are separate.
3. Runtime ground-truth laundering labels are not analyst-facing evidence.
4. Policy and case claims require retrieved evidence/citations. The bounded investigation workflow withholds unsupported output.

## Tool and agent boundaries

1. The Phase 12 agent uses a deterministic bounded plan and only these read-only tools: `case_overview`, `search_evidence`, `path_evidence`, `history_evidence`, `policy_search`, and `phase11_explanation`.
2. Action tools, shell access, direct code execution, account action, case closure, and regulatory filing are prohibited from that agent workflow.
3. A policy retrieval result supplies context for human review; it does not establish legal compliance or legal advice.

## Model and governance boundaries

1. Certified model artifacts are treated as read-only by later governance/reliability phases.
2. Feedback is append-only and is not automatically a training label.
3. Drift, performance observation, or a retraining proposal must not automatically retrain, recalibrate, promote a model, alter thresholds, or release a deployment.
4. Human approval is required for model-change and release decisions.

## Reliability and operational boundaries

1. Readiness, integrity, recovery, and SLO checks are contracts and testable controls—not proof of achieved production availability or latency.
2. In-process smoke checks do not prove external cloud networking, live traffic performance, or operational incident readiness.
3. Optional infrastructure configuration does not imply the corresponding service is running.

## Data boundaries

1. The documented core dataset is synthetic IBM AML-Data; the project must not be described as using real customer or banking data.
2. Data/model artifacts may be local and Git-ignored. Their presence in one workspace does not guarantee fresh-clone reproducibility.
3. Outputs are investigation-support signals, not guaranteed fraud/AML detection results.
