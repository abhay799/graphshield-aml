# GraphShield AML — Architecture

## System view

```mermaid
flowchart TB
    subgraph DATA["1. Data Foundation"]
        A1[Public / Synthetic Transactions]
        A2[Bronze / Silver]
        A3[Chronological Splits]
        A1 --> A2 --> A3
    end

    subgraph FEATURES["2. Point-in-Time Intelligence"]
        B1[History]
        B2[Velocity]
        B3[Counterparty]
        B4[Pair]
        B5[Concentration]
        B6[Graph Features]
    end

    A3 --> B1
    A3 --> B2
    A3 --> B3
    A3 --> B4
    A3 --> B5
    A3 --> B6

    subgraph MODEL["3. Risk Intelligence"]
        C1[Rules]
        C2[Logistic Regression]
        C3[LightGBM]
        C4[CatBoost]
        C5[TGN]
        C6[Calibration + Fusion]
        C7[Risk-Ranked Queue]
    end

    B1 --> C2
    B2 --> C3
    B3 --> C3
    B4 --> C3
    B5 --> C3
    B6 --> C3
    A3 --> C5

    C1 --> C6
    C2 --> C6
    C3 --> C6
    C4 --> C6
    C5 --> C6
    C6 --> C7

    subgraph INVESTIGATION["4. Investigation"]
        D1[Case Bundle]
        D2[Point-in-Time Graph]
        D3[Evidence Documents]
        D4[Policy Corpus]
        D5[Phase 11 Explainability]
        D6[Phase 12 Bounded Agent]
    end

    C7 --> D1
    D1 --> D2
    D1 --> D3
    D4 --> D6
    D5 --> D6
    D2 --> D6
    D3 --> D6

    subgraph CONTROL["5. Human Control + Governance"]
        E1[Human Analyst Review]
        E2[Audit Trail]
        E3[Feedback Adjudication]
        E4[Drift Monitoring]
        E5[Human-Gated Retraining Proposal]
    end

    D6 --> E1 --> E2 --> E3 --> E4 --> E5

    subgraph PRODUCT["6. Product + Platform"]
        F1[FastAPI]
        F2[Streamlit UI v2]
        F3[Docker / Kubernetes]
        F4[Readiness / Integrity]
        F5[Release / Recovery Gates]
    end

    C7 --> F1
    D5 --> F1
    D6 --> F1
    E4 --> F1
    F1 --> F2
    F3 --> F1
    F4 --> F1
    F5 --> F1
```

## Design principles

1. **Point-in-time correctness first** — model features must not use future information.
2. **Ranking instead of autonomous disposition** — GraphShield prioritizes analyst attention.
3. **Separate evidence channels** — deterministic reasons, model attribution, graph context, and policy context stay distinguishable.
4. **Fail closed for grounded generation** — unsupported claims should be withheld rather than improvised.
5. **Certified artifacts are immutable during later governance phases.**
6. **Humans own final case and regulatory decisions.**
7. **Deployment readiness is not the same as production performance.**
