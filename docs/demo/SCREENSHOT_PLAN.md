# GraphShield AML Screenshot Plan

This is a capture plan for a professional presentation package built from the actual running Streamlit application and the static portfolio page. Do not create fake screenshots or synthetic UI artifacts.

## Capture rules

- Only capture from the actual running application/browser.
- Do not include terminal windows, local paths, tokens, private data, or unrelated desktop UI.
- Keep viewport and browser zoom consistent.
- Preserve provenance labels where they are visible in the app.
- Prefer a clean, narrow browser viewport for presentation slides.
- Capture in a 16:9 presentation crop when possible.

## Required capture set

Planned screenshots: 10 total.

| # | Filename | Exact page/view | Purpose | What should be visible | Required labels / provenance | Must not appear | Composition |
|---|---|---|---|---|---|---|---|
| 1 | `01-portfolio-hero.png` | Static portfolio hero page | Show the project identity and framing | GraphShield AML headline, descriptor, CTA links, research/portfolio boundary | "Human-controlled", "Evidence-backed", "Synthetic/public data" | Fake marketing claims, unsupported production language | Full hero section with clean dark background and crisp typography |
| 2 | `02-mission-control.png` | Streamlit: AML Mission Control | Show the command center entry view | Mission control layout, risk queue, summary cards, case actions | `READ-ONLY`, `Human Review Required`, source provenance if visible | Terminal, local file paths, secrets, irrelevant desktop clutter | Wide layout, top-to-bottom command center view |
| 3 | `03-risk-alert-intelligence.png` | Streamlit: Risk / Alert Intelligence | Demonstrate queue prioritization | Ranked alert list, case meta, risk context, current view labels | `LOCAL READ-ONLY ARTIFACT` or `BACKEND API`, `READ-ONLY` | Any fake numbers or invented alerts | Capture the queue with a few visible rows only |
| 4 | `04-graph-explorer.png` | Streamlit: Graph Explorer | Show graph-based investigation context | Account/entity graph, edges, focal transaction, highlighted structure | `point-in-time evidence view`, `READ-ONLY`, `Human review required` | Proof of criminal conduct, fabricated labels | Center the graph and keep surrounding UI minimal |
| 5 | `05-case-investigation.png` | Streamlit: Case Investigation | Show the investigation shell around one case | Case ID, summary metadata, graph path, explanation area, risk context | case ID, `READ-ONLY`, `Human review required` | Local machine paths, unrelated browser tabs | Wide layout with evidence and case summary visible |
| 6 | `06-path-evidence-explorer.png` | Streamlit: Path / Evidence Explorer | Show evidence and connected path review | Path evidence, transaction context, connected entities, evidence cards | `Evidence is separated into factual graph evidence, interpretation, and policy context` | Fake charts without real data | Focus on path and evidence cards |
| 7 | `07-policy-evidence.png` | Streamlit: Policy / Regulatory Evidence | Demonstrate retrieval and support workflow | Policy cards, citations, retrieval outputs, references | `READ-ONLY`, `Policy references support analyst review` | Regulatory conclusion language, legal assertions | Keep policy context readable and compact |
| 8 | `08-model-detection-intelligence.png` | Streamlit: Model / Detection Intelligence | Show model explanation context | Model summary, feature/graph context, explanation status | `Model explanation context is recorded separately from case facts` | Any claim of a live deployment champion | Keep model explanation simple and honest |
| 9 | `09-investigator-decision-support.png` | Streamlit: Investigator Decision Support | Show AI-assisted evidence review without autonomous action | Bounded tool use, grounded answer, review summary, governance notes | `Human review required`, `READ-ONLY`, `Grounded response only` | Action buttons for blocking, filing, or case closure | Keep the secondary AI panel readable |
| 10 | `10-provenance-audit.png` | Streamlit: Provenance / Audit | Show evidence and governance boundaries | Audit status, provenance label, governance summary | `SYNTHETIC`, `HISTORICAL CERTIFICATION`, `NOT PROVEN LIVE`, `READ-ONLY` | Live production assurance claims | Focus on provenance banner and one audit panel |

## Suggested capture order

1. `01-portfolio-hero.png`
2. `02-mission-control.png`
3. `03-risk-alert-intelligence.png`
4. `04-graph-explorer.png`
5. `05-case-investigation.png`
6. `06-path-evidence-explorer.png`
7. `07-policy-evidence.png`
8. `08-model-detection-intelligence.png`
9. `09-investigator-decision-support.png`
10. `10-provenance-audit.png`

## Primary demonstration case

Use deterministic scenario `GS-AML-002` as the preferred case for live capture when possible.

Why it is useful:
- It highlights graph evidence and reverse-prior path review.
- It shows the investigation flow clearly in a short presentation.
- It keeps the story focused on evidence and human review instead of raw scoring.

Fallback case:
- `GS-AML-001` if the queue view or initial triage needs to be shown before the graph path view.

## Capture checklist for each screenshot

Before saving each image:

- confirm the intended page is visible
- confirm the source/provenance banner is visible
- confirm no unnecessary browser chrome is included
- confirm no secrets, tokens, or local machine paths are visible
- confirm the crop is readable at presentation scale

## What must never appear

- terminal prompts or local shell output
- `.env` values or API keys
- machine-specific paths
- unrelated local apps or notifications
- fake benchmark numbers or invented metric cards
- wording such as “production-ready,” “fully certified,” or “bank-deployed”
- legal conclusion language such as “guilty,” “confirmed fraud,” or “approved filing”

## Suggested intent for the final deck

The final slide deck should tell a professional story:

Problem -> architecture -> graph intelligence -> case investigation -> evidence -> governance -> human review -> research status

This is a technical and evidence-based review package, not a compliance claim deck.
