# Execution Lifecycle

This flow describes how one transaction or connected network becomes investigation support. It separates deterministic processing, machine scoring, retrieval assistance, and consequential human authority.

```mermaid
flowchart LR
    input[Transaction dataset or replay event] --> validate[Canonical validation\nDeterministic]
    validate --> pit[Point-in-time feature construction\nDeterministic]
    pit --> rules[Rule signals\nDeterministic]
    pit --> model[Tabular/graph model scoring\nMachine scoring]
    pit --> graph[Graph context and network analysis\nGraph processing]
    validate --> temporal[Temporal event/TGN context\nMachine scoring]
    rules --> rank[Frozen calibration/fusion and ranking\nDeterministic model composition]
    model --> rank
    graph --> rank
    temporal --> rank
    rank --> candidate[Alert or case candidate]
    candidate --> bundle[Case extraction: bundle, subgraph, paths, evidence]
    bundle --> explanation[Explanation: TreeSHAP, reason codes, graph and temporal context]
    bundle --> retrieval[Case/policy retrieval with citations\nRAG assistance]
    explanation --> bounded[Bounded, read-only investigation tools]
    retrieval --> bounded
    bounded --> review[Human investigator review]
    review --> decision[Human-owned case decision]
    review --> feedback[Adjudication/feedback and append-only audit]
    feedback --> governance[Drift/performance observation and human-gated proposal]
```

The LLM/RAG-related assistance is bounded to retrieval and grounded investigation support. It does not own scoring, case disposition, enforcement, or regulatory action. See [Safety Control Plane](SAFETY_CONTROL_PLANE.md).
