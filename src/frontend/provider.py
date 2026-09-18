from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import polars as pl
import requests

API_BASE = os.getenv("GRAPHSHIELD_API_URL", "http://127.0.0.1:8000").rstrip("/")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_QUEUE_PATH = PROJECT_ROOT / "data" / "processed" / "cases" / "case_queue.parquet"


def source_descriptor(source: str | None, state: str | None = None, note: str | None = None) -> dict[str, str]:
    source = source or "NOT_CONNECTED"
    state = state or {
        "BACKEND_API": "LIVE",
        "LOCAL_ARTIFACT": "MEASURED",
        "SYNTHETIC_DEMO": "SYNTHETIC",
        "STATIC": "STATIC_DEMO",
        "NOT_CONNECTED": "NOT_CONNECTED",
    }.get(source, "NOT_MEASURED")
    return {
        "source": source,
        "state": state,
        "note": note or "",
    }


def provenance_label(source: str | None) -> str:
    label = (source or "").strip()
    mapping = {
        "BACKEND_API": "BACKEND API",
        "LOCAL_ARTIFACT": "LOCAL READ-ONLY ARTIFACT",
        "SYNTHETIC_DEMO": "SYNTHETIC DATA",
        "STATIC": "STATIC DEMO",
        "NOT_CONNECTED": "NOT CONNECTED",
        "UNKNOWN": "NOT MEASURED",
        "LIVE API /cases": "BACKEND API",
        "LOCAL READ-ONLY CASE QUEUE": "LOCAL READ-ONLY ARTIFACT",
        "CASE SOURCE UNAVAILABLE": "NOT CONNECTED",
        "LIVE": "BACKEND API",
        "MEASURED": "LOCAL READ-ONLY ARTIFACT",
        "SYNTHETIC": "SYNTHETIC DATA",
        "STATIC_DEMO": "STATIC DEMO",
    }
    return mapping.get(label, label or "NOT MEASURED").upper()


def api_get(path: str, timeout: float = 2.0):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=timeout)
        if r.ok:
            try:
                return True, r.json()
            except Exception:
                return True, {"text": r.text}
        return False, {"status_code": r.status_code, "detail": r.text[:500]}
    except Exception as exc:
        return False, {"error": str(exc)}


def api_post(path: str, payload: dict, timeout: float = 45.0):
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=timeout)
        try:
            body = r.json()
        except Exception:
            body = {"text": r.text}
        return r.ok, body, r.status_code
    except Exception as exc:
        return False, {"error": str(exc)}, None


def load_real_case_queue():
    if not CASE_QUEUE_PATH.exists():
        return [], source_descriptor("NOT_CONNECTED", "NOT_CONNECTED", "Case queue artifact unavailable")

    try:
        df = pl.read_parquet(CASE_QUEUE_PATH)
    except Exception as exc:
        return [], source_descriptor("LOCAL_ARTIFACT", "NOT_MEASURED", f"error: {type(exc).__name__}: {exc}")

    if df.height == 0:
        return [], source_descriptor("LOCAL_ARTIFACT", "STATIC_DEMO", "Case queue artifact is empty")

    names = set(df.columns)
    case_col = next((c for c in ("case_id", "investigation_id", "alert_id") if c in names), None)
    tx_col = next((c for c in ("transaction_id", "focal_transaction_id") if c in names), None)
    risk_col = next((c for c in ("risk_score", "calibrated_score", "score", "priority_score") if c in names), None)
    rank_col = next((c for c in ("risk_rank", "rank", "priority_rank") if c in names), None)
    entity_col = next((c for c in ("account_id", "entity_id", "sender_id", "sender_account") if c in names), None)

    if case_col is None:
        return [], source_descriptor("LOCAL_ARTIFACT", "NOT_MEASURED", "Case queue schema unsupported")

    if rank_col:
        try:
            df = df.sort(rank_col)
        except Exception:
            pass

    rows = []
    for row in df.head(250).iter_rows(named=True):
        case_id = str(row.get(case_col, "") or "").strip()
        if not case_id:
            continue
        raw_score = row.get(risk_col) if risk_col else None
        try:
            score = float(raw_score)
            if score <= 1.0:
                score = score * 100.0
            score = round(score, 1)
        except Exception:
            score = None
        rows.append(
            {
                "case_id": case_id,
                "transaction_id": str(row.get(tx_col, "") or "") if tx_col else "",
                "risk_score": score,
                "risk_rank": row.get(rank_col) if rank_col else None,
                "entity": str(row.get(entity_col, "") or "") if entity_col else "",
                "raw": {k: row.get(k) for k in df.columns[:40]},
            }
        )
    return rows, source_descriptor("LOCAL_ARTIFACT", "MEASURED", "Read-only local case queue")


def load_api_cases(limit: int = 250):
    ok, payload = api_get(f"/cases?limit={limit}", timeout=6.0)
    if not ok or not isinstance(payload, dict):
        return [], source_descriptor("BACKEND_API", "NOT_CONNECTED", "case API unavailable")

    records = payload.get("cases")
    if not isinstance(records, list):
        return [], source_descriptor("BACKEND_API", "NOT_MEASURED", "Unexpected case schema")

    rows = []
    for item in records:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id") or item.get("investigation_id") or item.get("alert_id") or "").strip()
        if not case_id:
            continue
        txid = str(item.get("transaction_id") or item.get("focal_transaction_id") or "").strip()
        entity = str(
            item.get("account_id")
            or item.get("entity_id")
            or item.get("from_account_key")
            or item.get("sender_account")
            or item.get("sender")
            or ""
        ).strip()
        raw_score = (
            item.get("risk_score")
            if item.get("risk_score") is not None
            else item.get("calibrated_score")
            if item.get("calibrated_score") is not None
            else item.get("priority_score")
            if item.get("priority_score") is not None
            else item.get("score")
        )
        try:
            score = float(raw_score)
            if score <= 1.0:
                score *= 100.0
            score = round(score, 2)
        except Exception:
            score = None
        rows.append(
            {
                "case_id": case_id,
                "transaction_id": txid,
                "risk_score": score,
                "risk_rank": item.get("risk_rank") or item.get("rank") or item.get("priority_rank"),
                "entity": entity,
                "raw": item,
            }
        )
    return rows, source_descriptor("BACKEND_API", "LIVE", "Live /cases endpoint")


def case_catalog():
    api_rows, api_meta = load_api_cases()
    if api_rows:
        return api_rows, "LIVE API /cases", api_meta

    real_rows, local_meta = load_real_case_queue()
    if real_rows:
        return real_rows, "LOCAL READ-ONLY CASE QUEUE", local_meta

    return [], "CASE SOURCE UNAVAILABLE", source_descriptor("NOT_CONNECTED", "NOT_CONNECTED", "No accessible case source")


def real_case_ids():
    rows, mode, meta = case_catalog()
    return [r["case_id"] for r in rows], mode, meta


def fetch_case_graph(case_id: str, max_edges: int = 200):
    ok, payload = api_get(f"/cases/{case_id}/graph?max_edges={int(max_edges)}", timeout=20.0)
    if ok:
        return ok, payload, source_descriptor("BACKEND_API", "LIVE", f"Graph for {case_id}")
    return False, payload, source_descriptor("BACKEND_API", "NOT_CONNECTED", f"Graph unavailable for {case_id}")


def fetch_explainability(case_id: str, top_k: int = 5):
    ok, payload = api_get(f"/explainability/cases/{case_id}?top_k={top_k}", timeout=30.0)
    if ok:
        return ok, payload, source_descriptor("BACKEND_API", "LIVE", f"Explainability bundle for {case_id}")
    return False, payload, source_descriptor("BACKEND_API", "NOT_CONNECTED", f"Explainability unavailable for {case_id}")


def fetch_policy_context(case_id: str, question: str):
    ok, payload, status = api_post(
        "/phase12/investigations",
        {"case_id": case_id, "question": question.strip()},
        timeout=90.0,
    )
    if ok:
        return ok, payload, status, source_descriptor("BACKEND_API", "LIVE", f"Grounded policy context for {case_id}")
    return False, payload, status, source_descriptor("BACKEND_API", "NOT_CONNECTED", f"Policy investigation unavailable for {case_id}")


def fetch_governance_status():
    ok, payload = api_get("/phase13/status", timeout=4.0)
    if ok:
        return ok, payload, source_descriptor("BACKEND_API", "LIVE", "Governance status")
    return False, payload, source_descriptor("BACKEND_API", "NOT_CONNECTED", "Governance status unavailable")


def fetch_deployment_status():
    ok, payload = api_get("/deployment/integrity", timeout=4.0)
    if ok:
        return ok, payload, source_descriptor("BACKEND_API", "LIVE", "Deployment integrity")
    return False, payload, source_descriptor("BACKEND_API", "NOT_CONNECTED", "Deployment integrity unavailable")
