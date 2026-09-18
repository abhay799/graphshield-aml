# GraphShield AML Recording Guide

This guide describes how to record the actual GraphShield UI and static portfolio page without inventing fake screenshots or over-claiming production status.

## Before recording

### 1. Start required local services

Follow the documented startup flow from [docs/RUNNING.md](../RUNNING.md):

```powershell
cd <repo-folder>
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Then start the analyst UI:

```powershell
$env:GRAPHSHIELD_API_URL="http://127.0.0.1:8000"
python -m streamlit run src\frontend\app.py --server.port 8502
```

Optional static preview for the portfolio page:

```powershell
python -m http.server 8008 --directory "C:\Users\DELL\graphshield-aml\ui\portfolio"
```

### 2. Validate the deterministic scenario path

Run the repo scenario validation from the project root:

```powershell
python scripts/demo/run_scenarios.py --list
python scripts/demo/run_scenarios.py --scenario GS-AML-002
```

Use the deterministic demo case expected by the scenario runner and only mention scenario IDs when they are visibly supported by the repo.

### 3. Prepare the presentation environment

- close unrelated browser tabs and apps
- disable notifications
- hide local terminal windows from the capture area
- use a neutral desktop background
- keep the browser zoom consistent
- avoid showing local file explorer or personal/project directories
- confirm the app is showing the correct demo case and not a stale or missing state

## Browser preparation

Use a normal desktop browser and keep a predictable layout:

- browser size: approximately 1440 x 900 or 1600 x 900
- zoom: 100%
- clean tab bar
- no devtools open
- no visible local sensitive content
- leave the viewport stable for each capture

## Recommended recording order

Use this tab/page order for a clean presentation:

1. Static portfolio page
2. Streamlit AML Mission Control
3. Risk / Alert Intelligence
4. Graph Explorer
5. Case Investigation
6. Path / Evidence Explorer
7. Policy / Regulatory Evidence
8. Provenance / Audit
9. System / Research Status

This order is consistent with the problem-to-evidence storytelling arc and avoids random navigation.

## Required provenance and status labels

Ensure these labels remain visible when relevant:

- `SYNTHETIC`
- `BACKEND API`
- `LOCAL READ-ONLY ARTIFACT`
- `HISTORICAL CERTIFICATION`
- `NOT PROVEN LIVE`
- `Human review required`
- `READ-ONLY`

For any page using fallback behavior, label it clearly as local artifact or not connected rather than pretending it is live production.

## Failure fallback

If the API is unavailable:

- do not fake live data
- use the documented local-artifact/fallback behavior
- explicitly label the state in the screen
- continue with the static portfolio or a local artifact view

If the case or graph data is unavailable:

- use the deterministic scenario output and repository-backed evidence files
- explain that the presentation is using a static, read-only tested scenario
- do not imply live production data or faster-than-actual responses

## Audio / narration guidance

Narration should be short, calm, and technical.

Good patterns:
- explain the workflow and evidence boundary
- describe the graph context and human review step
- mention what is measured versus historical or synthetic

Avoid:
- reading every UI label verbatim
- making unsupported regulatory or legal claims
- overstating live deployment or production readiness

## Screenshot quality checklist

Before saving each screenshot:

- confirm the page is the correct one
- confirm the provenance banner or labels are in view
- confirm no local file paths or terminals are visible
- keep the page readable at standard presentation scale
- avoid empty states unless intentionally demonstrating fallback behavior
- do not include fake charts, invented metrics, or mock UI elements

## Final recording intention

The final material should feel like a technical evidence review package:

- realistic engineering workflow
- honest provenance
- human decision authority preserved
- synthetic/public research context clearly labeled
- no unsupported production claims
