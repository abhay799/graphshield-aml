# GraphShield Portfolio Finalization Checklist

## 1. Run the product

Terminal 1:
```powershell
.\.venv\Scripts\python.exe -m uvicorn api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Terminal 2:
```powershell
$env:GRAPHSHIELD_API_URL="http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run src\frontend\app.py --server.port 8502
```

Open:
```text
http://localhost:8502
```

## 2. Capture these screenshots

Save exactly as:

```text
docs/screenshots/01-command-center.png
docs/screenshots/02-case-queue.png
docs/screenshots/03-investigation.png
docs/screenshots/04-graph-explorer.png
docs/screenshots/05-explainability.png
docs/screenshots/06-ai-investigator.png
docs/screenshots/07-policy-rag.png
docs/screenshots/08-governance.png
docs/screenshots/09-deployment.png
```

Best three for the README:

```text
01-command-center.png
04-graph-explorer.png
06-ai-investigator.png
```

## 3. Verify repo changes before staging

```powershell
git status --short
git diff -- README.md docs\ARCHITECTURE.md docs\DEMO_SCRIPT.md docs\SCREENSHOT_PLAN.md docs\PROJECT_BOUNDARIES.md
```

## 4. Stage only intended portfolio files

Do NOT use `git add .`.

```powershell
git add README.md
git add docs\ARCHITECTURE.md
git add docs\DEMO_SCRIPT.md
git add docs\SCREENSHOT_PLAN.md
git add docs\PROJECT_BOUNDARIES.md
git add docs\screenshots\01-command-center.png
git add docs\screenshots\04-graph-explorer.png
git add docs\screenshots\06-ai-investigator.png
git add src\frontend\app.py
git add src\frontend\styles.css
```

Then inspect:

```powershell
git status --short
git diff --cached --stat
```

## 5. Commit only after the screenshots look correct

Suggested commit message:

```text
portfolio: finalize GraphShield UI v2 and project presentation
```
