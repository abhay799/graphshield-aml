# Evidence and Policy Flow

```mermaid
flowchart LR
    case[Selected case] --> relevant[Relevant transactions and history]
    case --> graph[Case subgraph and suspicious paths]
    relevant --> evidence[Evidence documents]
    graph --> evidence
    evidence --> caseindex[Case evidence index]

    question[Investigator policy/question context] --> policyquery[Policy query]
    policyquery --> policyindex[Policy corpus and indexes\nTF-IDF and dense retrieval]
    policyindex --> passages[Cited policy passages]

    caseindex --> grounded[Grounded case/policy evidence]
    passages --> grounded
    grounded --> explanation[Phase 11 explanation context]
    explanation --> agent[Phase 12 bounded investigation assistance]
    grounded --> agent
    agent --> investigator[Human investigator review]

    validation[Citation and grounding validation] -. validates .-> grounded
    failclosed[Withhold unsupported answer] -. constrains .-> agent
```

Policy retrieval provides documented context from the local corpus; it does not supply legal advice, certify compliance, or replace investigator verification. The bounded agent is limited to allowlisted read-only tools and consumes evidence rather than taking an external action.
