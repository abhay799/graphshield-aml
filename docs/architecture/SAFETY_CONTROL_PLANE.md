# Safety Control Plane

GraphShield is designed to turn machine outputs into reviewable evidence, not autonomous action.

```mermaid
flowchart TB
    output[Rules, model, graph, and temporal outputs] --> support[Decision support only]
    support --> evidence[Evidence, provenance, explanation, and policy context]
    evidence --> bounded[Bounded investigation assistance]
    bounded --> investigator[Human investigator]
    investigator --> decision[Human-owned decision]

    readonly[Read-only allowlisted tools] -. constrains .-> bounded
    grounding[Strict grounding and citation validation] -. constrains .-> bounded
    failclosed[Fail-closed grounding behavior] -. constrains .-> bounded
    audit[Hash-chain audit and append-only feedback] -. records .-> investigator
    labels[No automatic feedback-to-label promotion] -. constrains .-> support
    governance[Human-gated model/retraining proposals] -. constrains .-> support
    integrity[Artifact integrity and readiness gates] -. protects .-> output

    prohibited[Prohibited autonomous actions:\nSAR/STR filing, banking restriction, legal/regulatory decision, case closure]
```

The dashed safeguards are repository-supported controls: Phase 12 tool/grounding/audit contracts, Phase 13 governance contracts, and Phase 14 integrity checks. They do not constitute regulatory certification. The complete textual rules are in [Safety Invariants](SAFETY_INVARIANTS.md).
