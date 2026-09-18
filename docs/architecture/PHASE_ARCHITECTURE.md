# Phase Architecture

The repository history is cumulative: later phases depend on earlier artifacts and contracts. Status labels are evidence-oriented and historical certifications are not fresh verification claims.

```mermaid
flowchart TB
    bootstrap[Bootstrap / repository initialization\nNOT FOUND as a formal Phase 0] --> p1[Phase 1: Data Foundation\nIMPLEMENTED + VERIFIED historically]
    p1 --> p2[Phase 2: Features and Rules\nIMPLEMENTED + VERIFIED historically]
    p2 --> p3[Phase 3: Baseline ML\nIMPLEMENTED + VERIFIED historically]
    p2 --> p4[Phase 4: Graph Intelligence\nIMPLEMENTED + VERIFIED historically]
    p3 --> p5[Phase 5: Temporal Graph and Fusion\nIMPLEMENTED + VERIFIED historically]
    p4 --> p5
    p3 --> p6[Phase 6: Investigation and RAG\nIMPLEMENTED + VERIFIED historically]
    p4 --> p6
    p5 --> p6
    p6 --> p7[Phase 7: Service and Workbench Integration\nIMPLEMENTED + VERIFIED historically]
    p7 --> p8[Phase 8: Productization\nIMPLEMENTED BUT NOT FULLY VERIFIED currently]
    p8 --> p85[Phase 8.5: Platform Foundation\nIMPLEMENTED BUT NOT FULLY VERIFIED currently]
    p4 --> p9[Phase 9: Advanced Online Graph Intelligence\nIMPLEMENTED BUT NOT FULLY VERIFIED currently]
    p85 --> p9
    p5 --> p10[Phase 10: Streaming and Temporal Fusion\nIMPLEMENTED + VERIFIED historically]
    p85 --> p10
    p9 --> p10
    p10 --> p11[Phase 11: Explainable AML\nIMPLEMENTED + VERIFIED historically]
    p11 --> p12[Phase 12: Bounded Agentic Investigation\nIMPLEMENTED + VERIFIED historically]
    p6 --> p12
    p12 --> p13[Phase 13: Feedback, Drift, and Governance\nIMPLEMENTED + VERIFIED historically]
    p13 --> p14[Phase 14: Enterprise Runtime Readiness\nIMPLEMENTED + VERIFIED historically]
    p14 --> p15[Phase 15: Reliability and Final Release\nIMPLEMENTED + VERIFIED historically]
```

The detailed recovered status and supporting references are in [Phase Index](PHASE_INDEX.md). “Historically” means backed by committed reports, tests, and/or validation artifacts; it is not a claim that all gates were rerun for this documentation change.
