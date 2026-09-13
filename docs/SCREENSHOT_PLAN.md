# Portfolio Screenshot Plan

Create this directory in the repo:

```powershell
New-Item -ItemType Directory -Force docs\screenshots | Out-Null
```

Capture screenshots at `http://localhost:8502`.

## Required screenshots

| File | Screen | What must be visible |
|---|---|---|
| `01-command-center.png` | Command Center | GraphShield branding, live system, case metrics, guided demo path |
| `02-case-queue.png` | Case Queue | Ranked real case list, risk score/severity, live source badge |
| `03-investigation.png` | Investigation | selected case, live source, certified explanation button/results |
| `04-graph-explorer.png` | Graph Explorer | real materialized graph, node/edge counts, graph metadata |
| `05-explainability.png` | Explainability | Phase 11 schema/governance, explanation signals |
| `06-ai-investigator.png` | AI Investigator | case question, bounded tool list, grounded live response |
| `07-policy-rag.png` | Policy RAG | policy question, grounded answer/citation evidence |
| `08-governance.png` | Governance | Phase 13 status, drift, gate/retraining state |
| `09-deployment.png` | Deployment | `/live`, `/ready`, `/deployment`, integrity status |

## Best 3 for GitHub README

Use these above the fold:

1. `01-command-center.png`
2. `04-graph-explorer.png`
3. `06-ai-investigator.png`

## Capture rules

- Use one browser window at about 90–100% zoom.
- Hide unrelated tabs/bookmarks if possible.
- Do not include terminal errors in screenshots.
- Do not show any secret/API key.
- Prefer a case whose graph is eagerly materialized.
- Keep the left navigation visible so viewers understand the product scope.
- Do not crop away LIVE/READ-ONLY/HUMAN REVIEW labels.
- Never label synthetic/public data as real customer/bank data.

## README image block

After screenshots exist:

```markdown
## Product preview

### Analyst Command Center
![Command Center](docs/screenshots/01-command-center.png)

### Point-in-Time Graph Explorer
![Graph Explorer](docs/screenshots/04-graph-explorer.png)

### Bounded AI Investigator
![AI Investigator](docs/screenshots/06-ai-investigator.png)
```
