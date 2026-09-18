from __future__ import annotations

import os
from datetime import datetime
from html import escape
import math
from pathlib import Path

import pandas as pd
import polars as pl
import requests
import streamlit as st

from provider import (
    api_get,
    api_post,
    case_catalog,
    fetch_case_graph,
    fetch_explainability,
    fetch_governance_status,
    fetch_policy_context,
    provenance_label,
    real_case_ids,
    source_descriptor,
)

API_BASE = os.getenv("GRAPHSHIELD_API_URL", "http://127.0.0.1:8000").rstrip("/")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASE_QUEUE_PATH = PROJECT_ROOT / "data" / "processed" / "cases" / "case_queue.parquet"

st.set_page_config(
    page_title="GraphShield AML",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

def load_css() -> None:
    css_path = os.path.join(os.path.dirname(__file__), "styles.css")
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# The frontend now routes most read-only data access through src/frontend/provider.py.
# This keeps the existing UI behavior intact while narrowing the scattered data-loading pattern.


@st.cache_data(ttl=15, show_spinner=False)
def openapi_schema():
    ok, payload = api_get("/openapi.json", timeout=3.0)
    if ok and isinstance(payload, dict):
        return payload
    return {}

def discover_routes(*keywords: str):
    schema = openapi_schema()
    paths = schema.get("paths", {}) if isinstance(schema, dict) else {}
    words = [k.lower() for k in keywords if k]
    found = []
    for path, methods in paths.items():
        hay = path.lower()
        if words and not any(w in hay for w in words):
            continue
        method_names = []
        if isinstance(methods, dict):
            method_names = [m.upper() for m in methods.keys() if m.lower() in {"get","post","put","patch","delete"}]
        found.append((path, ", ".join(method_names) or "UNKNOWN"))
    return sorted(found)

def flatten_dict(value, prefix="", out=None, depth=0):
    if out is None:
        out = {}
    if depth > 3:
        return out
    if isinstance(value, dict):
        for key, val in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(val, (dict, list)):
                flatten_dict(val, name, out, depth + 1)
            else:
                out[name] = val
    elif isinstance(value, list):
        for i, val in enumerate(value[:10]):
            name = f"{prefix}[{i}]"
            if isinstance(val, (dict, list)):
                flatten_dict(val, name, out, depth + 1)
            else:
                out[name] = val
    return out

def first_value(payload, *names, default="—"):
    flat = flatten_dict(payload)
    wanted = {n.lower() for n in names}
    for key, value in flat.items():
        leaf = key.split(".")[-1].lower()
        if leaf in wanted:
            return value
    return default

def bool_label(value):
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if value is None:
        return "—"
    return str(value)

def endpoint_status_card(title: str, path: str, ok: bool, payload):
    state = "LIVE" if ok else "UNAVAILABLE"
    tone = "green" if ok else "red"
    summary = first_value(
        payload,
        "status", "overall_status", "result", "state",
        default="Endpoint responding" if ok else "Endpoint unavailable"
    )
    st.markdown(
        f"""
        <div class="live-endpoint-card endpoint-{tone}">
          <div class="live-endpoint-top">
            <span>{title}</span>
            <strong>{state}</strong>
          </div>
          <div class="live-endpoint-path">{path}</div>
          <div class="live-endpoint-summary">{summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _pick(d: dict, keys, default=None):
    if not isinstance(d, dict):
        return default
    for key in keys:
        if key and key in d and d[key] not in (None, ""):
            return d[key]
    return default

def normalize_graph_payload(payload: dict):
    if not isinstance(payload, dict):
        return [], []

    source_col = payload.get("source_column")
    target_col = payload.get("target_column")
    raw_edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
    raw_nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []

    edges = []
    node_ids = set()

    for i, edge in enumerate(raw_edges):
        if not isinstance(edge, dict):
            continue

        source = _pick(
            edge,
            ["source", "from", "source_id", "from_id", source_col, "from_account_key", "sender", "sender_id"],
        )
        target = _pick(
            edge,
            ["target", "to", "target_id", "to_id", target_col, "to_account_key", "receiver", "receiver_id"],
        )

        if source is None or target is None:
            continue

        source = str(source)
        target = str(target)
        node_ids.update([source, target])

        txid = _pick(edge, ["transaction_id", "tx_id", "event_id"], "")
        amount = _pick(edge, ["amount", "amount_paid", "amount_received", "value"], "")
        focal = bool(
            _pick(edge, ["is_focal", "focal", "is_focal_transaction"], False)
            or (
                payload.get("focal_transaction_id")
                and txid
                and str(txid) == str(payload.get("focal_transaction_id"))
            )
        )

        edges.append(
            {
                "source": source,
                "target": target,
                "transaction_id": str(txid) if txid not in (None, "") else "",
                "amount": amount,
                "focal": focal,
                "raw": edge,
            }
        )

    nodes = []
    for node in raw_nodes:
        if isinstance(node, str):
            node_id = node
            label = node
            raw = {"id": node}
        elif isinstance(node, dict):
            node_id = _pick(
                node,
                ["id", "node_id", "account_id", "account_key", "entity_id", "key", "label"],
            )
            if node_id is None:
                continue
            label = _pick(node, ["label", "name", "account_id", "entity_id"], node_id)
            raw = node
        else:
            continue

        node_id = str(node_id)
        node_ids.add(node_id)
        nodes.append({"id": node_id, "label": str(label), "raw": raw})

    known = {n["id"] for n in nodes}
    for node_id in sorted(node_ids - known):
        nodes.append({"id": node_id, "label": node_id, "raw": {}})

    return nodes, edges

def render_live_graph_svg(payload: dict, max_nodes: int = 40):
    nodes, edges = normalize_graph_payload(payload)

    if not nodes:
        return None, nodes, edges

    nodes = nodes[:max_nodes]
    allowed = {n["id"] for n in nodes}
    edges = [e for e in edges if e["source"] in allowed and e["target"] in allowed][:120]

    focal_nodes = set()
    for edge in edges:
        if edge.get("focal"):
            focal_nodes.update([edge["source"], edge["target"]])

    width, height = 820, 540
    cx, cy = width / 2, height / 2
    radius = min(width, height) * 0.36

    positions = {}
    n = len(nodes)
    for i, node in enumerate(nodes):
        if n == 1:
            x, y = cx, cy
        else:
            angle = (2 * math.pi * i / n) - math.pi / 2
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
        positions[node["id"]] = (x, y)

    lines = []
    for edge in edges:
        x1, y1 = positions[edge["source"]]
        x2, y2 = positions[edge["target"]]
        stroke = "#ff5364" if edge.get("focal") else "#345d8d"
        sw = "4" if edge.get("focal") else "1.8"
        lines.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{stroke}" stroke-width="{sw}" opacity="0.82"/>'
        )

    circles = []
    for node in nodes:
        x, y = positions[node["id"]]
        focal = node["id"] in focal_nodes
        fill = "#b92f4a" if focal else "#173a61"
        stroke = "#ff8490" if focal else "#4e9bff"
        label = escape(node["label"][:18])
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="24" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">●</text>'
            f'<text x="{x:.1f}" y="{y+41:.1f}" text-anchor="middle" fill="#dce9f8" font-size="10">{label}</text>'
        )

    svg = f"""
    <div class="graph-canvas live-graph-canvas">
      <svg viewBox="0 0 {width} {height}" width="100%" height="540" role="img" aria-label="GraphShield live case graph">
        <rect width="100%" height="100%" rx="18" fill="#081624"/>
        {''.join(lines)}
        {''.join(circles)}
      </svg>
      <div class="graph-legend">
        <span><i class="legend-dot legend-red"></i> Focal transaction endpoints / edge</span>
        <span><i class="legend-dot legend-blue"></i> Case network node</span>
      </div>
    </div>
    """
    return svg, nodes, edges

def live_case_graph(case_id: str, max_edges: int):
    return api_get(
        f"/cases/{case_id}/graph?max_edges={int(max_edges)}",
        timeout=20.0,
    )


def sev_tone(severity: str) -> str:
    return {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "amber", "LOW": "blue"}.get(severity, "blue")

def badge(text: str, tone: str = "blue") -> str:
    return f'<span class="badge badge-{tone}">{text}</span>'


def render_provenance_banner(title: str, source_label: str, state_label: str = "MEASURED", detail: str | None = None) -> None:
    source_text = provenance_label(source_label) if source_label else "NOT MEASURED"
    st.markdown(
        f"""
        <div class="live-endpoint-card endpoint-green" style="margin-bottom: 1rem;">
          <div class="live-endpoint-top">
            <span>{escape(str(title))}</span>
            <strong>{escape(str(state_label))}</strong>
          </div>
          <div class="live-endpoint-path">{escape(source_text)}</div>
          <div class="live-endpoint-summary">{escape(str(detail or 'Read-only GraphShield data path; analyst review remains required.'))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar() -> str:
    with st.sidebar:
        st.markdown(
            """
            <div class="brand-wrap">
              <div class="brand-shield">🛡️</div>
              <div>
                <div class="brand-title">GraphShield</div>
                <div class="brand-subtitle">AI-Powered AML</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        rows, source_mode, source_meta = case_catalog()

        st.markdown('<div class="side-section">ANALYST WORKSPACE</div>', unsafe_allow_html=True)

        pages = [
            "AML Mission Control",
            "Command Center",
            "Case Queue",
            "Transaction Intelligence",
            "Entity / Counterparty Intelligence",
            "Graph Explorer",
            "Suspicious Network Detection",
            "Risk / Alert Intelligence",
            "Case Investigation",
            "Investigation",
            "Path / Evidence Explorer",
            "Policy / Regulatory Evidence",
            "Policy RAG",
            "Model / Detection Intelligence",
            "Explainability",
            "Investigator Decision Support",
            "AI Investigator",
            "Provenance / Audit",
            "Governance",
            "System / Research Status",
            "Deployment",
        ]

        if "nav" not in st.session_state:
            st.session_state.nav = "AML Mission Control"

        pending_nav = st.session_state.pop("_pending_nav", None)
        if pending_nav:
            st.session_state.nav = pending_nav

        st.radio(
            "Navigation",
            pages,
            key="nav",
            label_visibility="collapsed",
        )

        st.markdown('<div class="side-section">DEMO FLOW</div>', unsafe_allow_html=True)

        if rows:
            first_case = rows[0]["case_id"]
            if st.button("▶ Start guided case demo", width="stretch", key="guided_demo_start"):
                st.session_state.selected_case_id = first_case
                st.session_state["_pending_nav"] = "Investigation"
                st.rerun()
        else:
            st.button("▶ Start guided case demo", width="stretch", disabled=True)
            st.caption("Case source unavailable.")

        st.markdown('<div class="side-spacer"></div>', unsafe_allow_html=True)
        st.markdown('<div class="side-section">SYSTEM</div>', unsafe_allow_html=True)

        source_class = "source-live" if rows else "source-offline"
        st.markdown(
            f'<div class="sidebar-source {source_class}">● {escape(source_mode)}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"API: {API_BASE}")
        st.caption("GraphShield UI v2 • Batch 7 • Live-first")

    return st.session_state.nav

def goto(page: str, case_id: str | None = None) -> None:
    # Do not mutate the widget-backed "nav" key after its radio widget exists.
    # Queue the destination and apply it before widget creation on the next rerun.
    st.session_state["_pending_nav"] = page
    if case_id:
        st.session_state.selected_case_id = case_id
    st.rerun()


def topbar(api_ok: bool) -> None:
    now = datetime.now().strftime("%d %b %Y • %I:%M %p")
    rows, source_mode, _ = case_catalog()

    left, right = st.columns([2.2, 1])

    with left:
        query = st.text_input(
            "Global case search",
            placeholder="Search case ID, transaction ID or entity...",
            label_visibility="collapsed",
            key="global_case_search",
        )

        if query.strip():
            q = query.strip().lower()
            matches = [
                r for r in rows
                if q in (
                    f'{r.get("case_id","")} '
                    f'{r.get("transaction_id","")} '
                    f'{r.get("entity","")}'
                ).lower()
            ][:8]

            if matches:
                labels = [
                    f'{r["case_id"]}  •  {r.get("entity") or r.get("transaction_id") or "case"}'
                    for r in matches
                ]
                selected_label = st.selectbox(
                    "Search results",
                    labels,
                    label_visibility="collapsed",
                    key="global_case_result",
                )
                selected_idx = labels.index(selected_label)
                selected_case = matches[selected_idx]["case_id"]

                if st.button(
                    "Open selected case →",
                    width="stretch",
                    key="global_open_case",
                ):
                    goto("Investigation", selected_case)
            else:
                st.caption("No case matches the current search.")

    with right:
        state = "LIVE SYSTEM" if api_ok else "API OFFLINE"
        state_cls = "status-live" if api_ok else "status-offline"

        st.markdown(
            f"""
            <div class="topbar-final">
              <div>
                <span class="{state_cls}">● {state}</span>
                <span class="source-chip">{escape(source_mode)}</span>
              </div>
              <div class="topbar-final-right">
                <span class="top-date">{now}</span>
                <span class="analyst-chip">AK</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

def command_center(api_ok: bool) -> None:
    rows, source_mode, _ = case_catalog()
    render_provenance_banner("AML Mission Control", source_mode, "READ-ONLY", "Decision support workspace. Analyst review remains mandatory.")
    scores = [r["risk_score"] for r in rows if isinstance(r.get("risk_score"), (int, float))]
    high = sum(1 for s in scores if s >= 75)
    critical = sum(1 for s in scores if s >= 90)
    entities = len({r.get("entity") for r in rows if r.get("entity")})
    median = round(float(pd.Series(scores).median()), 1) if scores else "—"

    st.markdown(
        """
        <div class="hero">
          <div>
            <div class="eyebrow">GRAPH-NATIVE FINANCIAL CRIME INTELLIGENCE</div>
            <h1>Good morning, Analyst.</h1>
            <p>Start with the highest-risk activity, inspect network evidence, then review grounded explanations before any human decision.</p>
          </div>
          <div class="hero-chip">Decision Support • Human Review Required</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("High-Risk Cases", str(high), f"{critical} critical in current queue", "⚠", "red"),
        ("Visible Cases", str(len(rows)), source_mode, "◫", "amber"),
        ("Unique Entities", str(entities) if entities else "—", f"Median risk {median}", "◎", "green"),
        ("Platform Health", "ONLINE" if api_ok else "OFFLINE", "Backend responding" if api_ok else "API not reachable", "♥", "blue"),
    ]
    for col, (title, value, sub, icon, tone) in zip((c1, c2, c3, c4), cards):
        with col:
            st.markdown(
                f"""
                <div class="metric-card metric-{tone}">
                  <div class="metric-icon">{icon}</div>
                  <div>
                    <div class="metric-title">{title}</div>
                    <div class="metric-value">{value}</div>
                    <div class="metric-subtitle">{escape(str(sub))}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    first_case = rows[0]["case_id"] if rows else None

    st.markdown('<div class="section-title">Start here</div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns(3)
    with a1:
        st.markdown('<div class="action-card"><div class="action-icon">📋</div><div class="action-copy"><div class="action-title">Review High-Risk Cases</div><div class="action-subtitle">Open the current prioritized analyst queue.</div></div><div class="action-arrow">→</div></div>', unsafe_allow_html=True)
        if st.button("Open Case Queue", width="stretch", key="cc_queue"):
            goto("Case Queue")
    with a2:
        st.markdown('<div class="action-card"><div class="action-icon">🔎</div><div class="action-copy"><div class="action-title">Continue Investigation</div><div class="action-subtitle">Review a real case from signal to evidence.</div></div><div class="action-arrow">→</div></div>', unsafe_allow_html=True)
        if st.button("Open Investigation", width="stretch", key="cc_inv", disabled=first_case is None):
            goto("Investigation", first_case)
    with a3:
        st.markdown('<div class="action-card"><div class="action-icon">🕸️</div><div class="action-copy"><div class="action-title">Explore Case Network</div><div class="action-subtitle">Load the materialized point-in-time case graph.</div></div><div class="action-arrow">→</div></div>', unsafe_allow_html=True)
        if st.button("Open Graph Explorer", width="stretch", key="cc_graph", disabled=first_case is None):
            goto("Graph Explorer", first_case)

    left, right = st.columns([1.55, 1])

    with left:
        st.markdown('<div class="panel-title">Current queue risk distribution</div>', unsafe_allow_html=True)
        if scores:
            buckets = {
                "Critical ≥90": sum(1 for s in scores if s >= 90),
                "High 75–89": sum(1 for s in scores if 75 <= s < 90),
                "Medium 50–74": sum(1 for s in scores if 50 <= s < 75),
                "Lower <50": sum(1 for s in scores if s < 50),
            }
            risk_df = pd.DataFrame(
                {"Cases": list(buckets.values())},
                index=list(buckets.keys()),
            )
            st.bar_chart(risk_df, height=290)
        else:
            st.info("Risk scores are not exposed by the current case endpoint.")

    with right:
        st.markdown('<div class="panel-title">Highest-priority visible cases</div>', unsafe_allow_html=True)
        sorted_rows = sorted(
            rows,
            key=lambda r: (
                r.get("risk_rank") if isinstance(r.get("risk_rank"), (int, float)) else 10**12,
                -(r.get("risk_score") if isinstance(r.get("risk_score"), (int, float)) else -1),
            ),
        )
        for case in sorted_rows[:5]:
            score = case.get("risk_score")
            severity = "CRITICAL" if isinstance(score, (int, float)) and score >= 90 else "HIGH" if isinstance(score, (int, float)) and score >= 75 else "REVIEW"
            tone = sev_tone(severity)
            st.markdown(
                f"""
                <div class="alert-row">
                  <div class="alert-dot alert-{tone}">!</div>
                  <div class="alert-copy">
                    <div class="alert-title">{escape(case["case_id"])}</div>
                    <div class="alert-meta">{escape(case.get("entity") or case.get("transaction_id") or "Case record")}</div>
                  </div>
                  <div class="alert-right">{badge(severity, tone)}<div class="alert-age">{score if score is not None else "—"}</div></div>
                </div>
                """,
                unsafe_allow_html=True,
            )


    st.markdown('<div class="section-title">Guided demo path</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="demo-flow">
          <div class="demo-step"><span>1</span><strong>Queue</strong><small>Pick a prioritized case</small></div>
          <div class="demo-arrow">→</div>
          <div class="demo-step"><span>2</span><strong>Investigate</strong><small>Review case context</small></div>
          <div class="demo-arrow">→</div>
          <div class="demo-step"><span>3</span><strong>Graph</strong><small>Inspect network evidence</small></div>
          <div class="demo-arrow">→</div>
          <div class="demo-step"><span>4</span><strong>Explain</strong><small>Read model + reason evidence</small></div>
          <div class="demo-arrow">→</div>
          <div class="demo-step"><span>5</span><strong>AI + Policy</strong><small>Grounded review with citations</small></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Live integration status</div>', unsafe_allow_html=True)

    p11 = bool(discover_routes("explainability", "phase11"))
    p12_tools_ok, _p12 = api_get("/phase12/tools", timeout=3.0)
    p13_ok, _p13 = api_get("/phase13/status", timeout=3.0)
    p14_ok, _p14 = api_get("/deployment/integrity", timeout=3.0)

    status_cols = st.columns(5)
    checks = [
        ("Cases", bool(rows), source_mode),
        ("Explainability", p11, "Phase 11"),
        ("AI Investigator", p12_tools_ok, "Phase 12"),
        ("Governance", p13_ok, "Phase 13"),
        ("Integrity", p14_ok, "Phase 14/15"),
    ]
    for col, (label, ok, detail) in zip(status_cols, checks):
        with col:
            state = "LIVE" if ok else "OFFLINE"
            tone = "integration-live" if ok else "integration-offline"
            st.markdown(
                f"""
                <div class="integration-card {tone}">
                  <span>{escape(label)}</span>
                  <strong>{state}</strong>
                  <small>{escape(str(detail))}</small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        f"Dashboard source: {source_mode}. "
        "Batch 7 does not fabricate a case, graph, explanation, or AI answer when a live source is unavailable."
    )

def case_queue() -> None:
    rows, source_mode, _ = case_catalog()
    render_provenance_banner("Risk / Alert Intelligence", source_mode, "READ-ONLY", "Queue view sourced from the current GraphShield case data path.")
    live_mode = bool(rows)

    st.markdown(f"""
    <div class="hero compact-hero">
      <div>
        <div class="eyebrow">ANALYST WORKSPACE</div>
        <h1>📋 Case Queue</h1>
        <p>Prioritize the highest-risk cases and open one investigation at a time.</p>
      </div>
      <div class="hero-chip">{source_mode} • Read only</div>
    </div>""", unsafe_allow_html=True)

    if not rows:
        st.error(
            "GraphShield has no available case source. "
            "The UI will not fabricate cases in live-first mode."
        )
        st.caption(
            "Expected source: GET /cases or the read-only local "
            "data/processed/cases/case_queue.parquet artifact."
        )
        return

    scores = [r["risk_score"] for r in rows if isinstance(r.get("risk_score"), (int, float))]
    high_count = sum(1 for s in scores if s >= 75)
    critical_count = sum(1 for s in scores if s >= 90)
    median_score = round(float(pd.Series(scores).median()), 1) if scores else "—"

    k1, k2, k3, k4 = st.columns(4)
    summary = [
        ("Visible cases", str(len(rows))),
        ("Critical ≥90", str(critical_count)),
        ("High ≥75", str(high_count)),
        ("Median risk", str(median_score)),
    ]
    for col, (a, b) in zip((k1, k2, k3, k4), summary):
        with col:
            st.markdown(
                f'<div class="mini-stat"><span>{a}</span><strong>{b}</strong></div>',
                unsafe_allow_html=True,
            )

    query = st.text_input(
        "Search",
        placeholder="Search case ID, transaction ID or entity",
        label_visibility="collapsed",
        key="live_case_search",
    )

    shown = 0
    for row in rows[:100]:
        searchable = f'{row.get("case_id","")} {row.get("transaction_id","")} {row.get("entity","")}'.lower()
        if query and query.lower() not in searchable:
            continue

        shown += 1
        score = row.get("risk_score")
        if isinstance(score, (int, float)):
            severity = "CRITICAL" if score >= 90 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
            score_text = f"{score:g}"
        else:
            severity = "REVIEW"
            score_text = "—"

        tone = sev_tone(severity)
        entity = row.get("entity") or "Case entity"
        tx = row.get("transaction_id") or "Transaction not exposed"

        left, mid, right = st.columns([4.1, 2.0, 1.25])
        with left:
            st.markdown(
                f"""
                <div class="case-card-left">
                  <div class="case-topline">{badge(severity, tone)} <span class="case-id">{row["case_id"]}</span></div>
                  <div class="case-entity">{entity}</div>
                  <div class="case-meta">{tx}</div>
                  <div class="case-summary">
                    {escape(source_mode)}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with mid:
            st.markdown(
                f"""
                <div class="case-score-panel">
                  <div class="score-number">{score_text}</div>
                  <div class="score-label">Risk score</div>
                  <div class="score-status">{source_mode}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with right:
            st.write("")
            if st.button("Investigate →", key=f'live_open_{row["case_id"]}', width="stretch"):
                st.session_state.selected_case_id = row["case_id"]
                if row.get("transaction_id"):
                    st.session_state.selected_transaction_id = row["transaction_id"]
                goto("Investigation", row["case_id"])

        st.markdown('<div class="case-divider"></div>', unsafe_allow_html=True)

    if shown == 0:
        st.info("No cases match the current search.")

    if rows:
        st.caption(
            f"Case source: {source_mode}. UI v2 reads case data only; certified model artifacts are not modified."
        )
    else:
        st.error(
            "No case source is available. Keep the API running or verify "
            "data/processed/cases/case_queue.parquet."
        )



def get_selected_case():
    rows, source_mode, _ = case_catalog()
    selected = st.session_state.get("selected_case_id")

    if not selected and rows:
        selected = rows[0]["case_id"]
        st.session_state.selected_case_id = selected

    if not selected:
        return {
            "case_id": "",
            "entity": "No case selected",
            "account": "",
            "severity": "UNAVAILABLE",
            "risk_score": "—",
            "status": "Unavailable",
            "country": "Not inferred",
            "entity_type": "Not inferred",
            "opened": "—",
            "analyst": "Human analyst",
            "summary": "No live case source is available.",
            "factors": [],
            "transactions": [],
            "evidence": [],
        }

    matched = next((r for r in rows if r["case_id"] == selected), None)

    if matched is None and rows:
        selected = rows[0]["case_id"]
        st.session_state.selected_case_id = selected
        matched = rows[0]

    if matched is None:
        return {
            "case_id": selected,
            "entity": "Case not found",
            "account": "",
            "severity": "UNAVAILABLE",
            "risk_score": "—",
            "status": "Unavailable",
            "country": "Not inferred",
            "entity_type": "Not inferred",
            "opened": "—",
            "analyst": "Human analyst",
            "summary": "The selected case is not available from the current source.",
            "factors": [],
            "transactions": [],
            "evidence": [],
        }

    score = matched.get("risk_score")
    numeric_score = score if isinstance(score, (int, float)) else None

    severity = (
        "CRITICAL" if numeric_score is not None and numeric_score >= 90
        else "HIGH" if numeric_score is not None and numeric_score >= 75
        else "MEDIUM" if numeric_score is not None and numeric_score >= 50
        else "REVIEW"
    )

    return {
        "case_id": selected,
        "entity": matched.get("entity") or matched.get("transaction_id") or "GraphShield case",
        "account": matched.get("entity") or "",
        "severity": severity,
        "risk_score": numeric_score if numeric_score is not None else "—",
        "status": "Analyst Review",
        "country": "Not inferred",
        "entity_type": "Not inferred",
        "opened": "From case queue",
        "analyst": "Human analyst",
        "summary": f"Live GraphShield case loaded from {source_mode}.",
        "factors": [],
        "transactions": [],
        "evidence": [],
    }

def investigation() -> None:
    c = get_selected_case()
    case_id = c["case_id"]
    rows, source_mode, _ = case_catalog()
    render_provenance_banner("Case Investigation", source_mode, "READ-ONLY", "Evidence and graph review remain analyst-controlled.")

    if not case_id:
        st.error(
            "No case is available for investigation. "
            "Keep the GraphShield API running or restore the read-only case queue artifact."
        )
        return
    raw_case = next((r for r in rows if r["case_id"] == case_id), None)
    raw = raw_case.get("raw", {}) if raw_case else {}

    st.markdown(
        f"""
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">CASE INVESTIGATION • {escape(case_id)}</div>
            <h1>🔎 {escape(str(c["entity"]))}</h1>
            <p>Evidence-led analyst workspace for the selected GraphShield case.</p>
          </div>
          <div class="hero-chip">{escape(source_mode)} • Human review required</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    score = c.get("risk_score")
    top = [
        ("Risk Score", f"{score}/100" if isinstance(score, (int, float)) else "—"),
        ("Severity", c.get("severity", "REVIEW")),
        ("Case ID", case_id),
        ("Source", source_mode),
    ]
    cols = st.columns(4)
    for col, (label, value) in zip(cols, top):
        with col:
            st.markdown(
                f'<div class="mini-stat"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>',
                unsafe_allow_html=True,
            )

    tabs = st.tabs(["Overview", "Transactions / Graph", "Evidence", "Policy", "Analyst Notes"])

    with tabs[0]:
        left, right = st.columns([1, 1.6])

        with left:
            st.markdown('<div class="panel-heading">Case record</div>', unsafe_allow_html=True)
            preferred = [
                "case_id", "risk_rank", "risk_score", "transaction_id",
                "focal_transaction_id", "from_account_key", "to_account_key",
                "event_ts", "amount_paid", "amount_received",
            ]
            shown = 0
            for key in preferred:
                if key in raw and raw[key] not in (None, ""):
                    st.markdown(
                        f'<div class="detail-row"><span>{escape(key)}</span><strong>{escape(str(raw[key]))}</strong></div>',
                        unsafe_allow_html=True,
                    )
                    shown += 1
            if shown == 0:
                st.caption("The current case endpoint exposes a minimal record. Use Explainability for the evidence bundle.")

            st.markdown('<div class="panel-heading">Recommended workflow</div>', unsafe_allow_html=True)
            st.markdown(
                """
                <div class="next-step-card"><div class="step-num">1</div><div><strong>Load explanation</strong><span>Review model attribution and observed reason codes separately.</span></div></div>
                <div class="next-step-card"><div class="step-num">2</div><div><strong>Inspect graph</strong><span>Review the materialized point-in-time network around the case.</span></div></div>
                <div class="next-step-card"><div class="step-num">3</div><div><strong>Check policy context</strong><span>Use cited policy retrieval before analyst disposition.</span></div></div>
                """,
                unsafe_allow_html=True,
            )

        with right:
            st.markdown('<div class="panel-heading">Live Phase 11 intelligence</div>', unsafe_allow_html=True)

            if st.button("Load certified explanation", type="primary", width="stretch", key=f"inv_explain_{case_id}"):
                ok, payload = api_get(
                    f"/explainability/cases/{case_id}?top_k=5",
                    timeout=30.0,
                )
                st.session_state[f"inv_exp_{case_id}"] = {"ok": ok, "payload": payload}

            exp = st.session_state.get(f"inv_exp_{case_id}")
            if exp:
                if exp["ok"]:
                    payload = exp["payload"]
                    summary = first_value(payload, "analyst_summary", "summary", "explanation_summary", default=None)
                    if summary:
                        st.markdown(
                            f'<div class="evidence-big"><div class="evidence-big-type">Analyst summary</div><div>{escape(str(summary))}</div></div>',
                            unsafe_allow_html=True,
                        )

                    flat = flatten_dict(payload)
                    candidates = []
                    for key, value in flat.items():
                        if any(tok in key.lower() for tok in ("reason", "driver", "feature", "shap", "graph", "temporal", "fusion", "risk")):
                            candidates.append((key, value))
                    for key, value in candidates[:16]:
                        st.markdown(
                            f'<div class="evidence-row"><span class="evidence-type">{escape(key.split(".")[-1])}</span><span class="evidence-text">{escape(str(value))}</span></div>',
                            unsafe_allow_html=True,
                        )

                    if not candidates and not summary:
                        st.json(payload)
                else:
                    st.error("Could not load Phase 11 explanation for this case.")
                    st.json(exp["payload"])
            else:
                st.info("Click **Load certified explanation** to retrieve the live Phase 11 case bundle.")

            a, b = st.columns(2)
            with a:
                if st.button("🕸 Open Graph Explorer", width="stretch", key="inv_graph_live"):
                    goto("Graph Explorer", case_id)
            with b:
                if st.button("🤖 Ask AI Investigator", width="stretch", key="inv_ai_live"):
                    goto("AI Investigator", case_id)

    with tabs[1]:
        st.markdown('<div class="panel-heading">Materialized point-in-time case graph</div>', unsafe_allow_html=True)
        if st.button("Load graph transactions", width="stretch", key=f"inv_graph_tx_{case_id}"):
            ok, payload = live_case_graph(case_id, 200)
            st.session_state[f"inv_graph_payload_{case_id}"] = {"ok": ok, "payload": payload}

        graph_result = st.session_state.get(f"inv_graph_payload_{case_id}")
        if graph_result:
            if graph_result["ok"]:
                payload = graph_result["payload"]
                _, _, edges = render_live_graph_svg(payload)
                if edges:
                    edge_df = pd.DataFrame(
                        [
                            {
                                "Source": e["source"],
                                "Target": e["target"],
                                "Transaction": e["transaction_id"],
                                "Amount": e["amount"],
                                "Focal": e["focal"],
                            }
                            for e in edges
                        ]
                    )
                    st.dataframe(edge_df, width="stretch", hide_index=True)
                else:
                    st.info("The graph endpoint returned no displayable edge records.")
            else:
                st.error("Graph endpoint unavailable for this case.")
                st.json(graph_result["payload"])
        else:
            st.caption("Load the case graph to view the exact transaction edges exposed by the backend.")

    with tabs[2]:
        exp = st.session_state.get(f"inv_exp_{case_id}")
        if exp and exp["ok"]:
            st.json(exp["payload"])
        else:
            st.info("Load the certified explanation in the Overview tab to inspect the full evidence bundle.")

    with tabs[3]:
        st.markdown(
            """
            <div class="policy-card">
              <strong>Policy-grounded investigation</strong>
              <span>GraphShield uses the bounded Phase 12 investigation path to retrieve relevant policy context with citations.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("📚 Open Policy RAG", width="stretch", key="inv_policy"):
            goto("Policy RAG", case_id)
        st.warning("Policy retrieval supports analyst review; it does not make a legal or regulatory determination.")

    with tabs[4]:
        note_key = f"note_{case_id}"
        saved_key = f"saved_note_{case_id}"

        note_value = st.text_area(
            "Analyst note",
            placeholder="Record observations, countervailing evidence, or follow-up questions...",
            height=170,
            key=note_key,
        )

        if st.button("Save session draft", width="stretch", key=f"save_note_{case_id}"):
            st.session_state[saved_key] = note_value
            st.success(
                "Draft saved in this Streamlit session only. "
                "Nothing was written to the GraphShield case store."
            )

        if st.session_state.get(saved_key):
            st.caption("Session draft available. It will disappear when the Streamlit session is reset.")

        st.caption(
            "Read-only portfolio mode: certified evidence, case history, and model artifacts remain untouched."
        )


def graph_explorer() -> None:
    c = get_selected_case()
    case_ids, case_mode, _ = real_case_ids()
    render_provenance_banner("Graph Explorer", case_mode, "READ-ONLY", "The graph is a point-in-time evidence view and not a proof of illicit activity.")
    if not case_ids:
        st.error("No live case source is available for Graph Explorer.")
        return
    selected_default = c["case_id"] if c["case_id"] in case_ids else (case_ids[0] if case_ids else c["case_id"])

    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">PHASE 7 • LIVE NETWORK INTELLIGENCE</div>
            <h1>🕸️ Graph Explorer</h1>
            <p>Load the actual materialized point-in-time case graph exposed by the GraphShield backend.</p>
          </div>
          <div class="hero-chip">LIVE /cases/{case_id}/graph • Read only</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.8, 1])
    with c1:
        selected_case = st.selectbox(
            "Case",
            options=case_ids or [selected_default],
            index=(case_ids.index(selected_default) if selected_default in case_ids else 0),
            key="graph_case_select_live",
        )
        st.session_state.selected_case_id = selected_case
    with c2:
        max_edges = st.slider("Maximum displayed edges", 25, 500, 150, 25)

    if st.button("Load live case graph", type="primary", width="stretch", key="load_live_graph"):
        with st.spinner("Loading materialized case graph..."):
            ok, payload = live_case_graph(selected_case, max_edges)
        st.session_state["live_graph_result"] = {
            "case_id": selected_case,
            "ok": ok,
            "payload": payload,
        }

    result = st.session_state.get("live_graph_result")
    if not result or result.get("case_id") != selected_case:
        st.info("Choose a case and click **Load live case graph**.")
        st.caption(f"Case source: {case_mode}")
        return

    if not result["ok"]:
        payload = result["payload"]
        detail = str(payload.get("detail") or payload.get("error") or payload)
        if "not eagerly materialized" in detail.lower() or "materialized" in detail.lower():
            st.info(
                "This case is in the analyst queue but its graph is not part of the eagerly materialized investigation set. "
                "Choose another high-ranked case or materialize it through the project pipeline."
            )
        else:
            st.error("The live graph endpoint did not return a successful response.")
            st.json(payload)
        return

    payload = result["payload"]
    svg, nodes, edges = render_live_graph_svg(payload)

    m1, m2, m3, m4 = st.columns(4)
    metrics = [
        ("Displayed nodes", payload.get("displayed_nodes", len(nodes))),
        ("Displayed edges", payload.get("displayed_edges", len(edges))),
        ("Total case edges", payload.get("total_subgraph_edges", len(edges))),
        ("Risk score", payload.get("risk_score", "—")),
    ]
    for col, (label, value) in zip((m1, m2, m3, m4), metrics):
        with col:
            st.markdown(
                f'<div class="mini-stat"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>',
                unsafe_allow_html=True,
            )

    left, right = st.columns([1.75, 1])

    with left:
        st.markdown('<div class="panel-heading">Point-in-time transaction network</div>', unsafe_allow_html=True)
        if svg:
            st.markdown(svg, unsafe_allow_html=True)
        else:
            st.warning("The graph response contained no displayable nodes.")

        st.markdown('<div class="panel-heading">Displayed transactions</div>', unsafe_allow_html=True)
        if edges:
            edge_df = pd.DataFrame(
                [
                    {
                        "Source": e["source"],
                        "Target": e["target"],
                        "Transaction": e["transaction_id"],
                        "Amount": e["amount"],
                        "Focal": e["focal"],
                    }
                    for e in edges
                ]
            )
            st.dataframe(edge_df, width="stretch", hide_index=True)
        else:
            st.caption("No normalized edges were returned.")

    with right:
        st.markdown('<div class="panel-heading">Graph metadata</div>', unsafe_allow_html=True)
        metadata = [
            ("Case", payload.get("case_id", selected_case)),
            ("Focal transaction", payload.get("focal_transaction_id", "—")),
            ("Risk rank", payload.get("risk_rank", "—")),
            ("Risk score", payload.get("risk_score", "—")),
            ("Source column", payload.get("source_column", "—")),
            ("Target column", payload.get("target_column", "—")),
            ("Materialized", payload.get("materialized", "—")),
        ]
        st.markdown('<div class="detail-card">', unsafe_allow_html=True)
        for label, value in metadata:
            st.markdown(
                f'<div class="detail-row"><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="panel-heading">Interpretation boundary</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="safety-card">
              <div>✓ Graph is a point-in-time evidence view</div>
              <div>✓ Network proximity is not proof of illicit activity</div>
              <div>✓ Focal transaction is visually distinguished</div>
              <div>✓ Analyst review remains mandatory</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("🤖 Ask AI about this case", width="stretch", key="graph_ai_live"):
            goto("AI Investigator", selected_case)
        if st.button("← Back to Investigation", width="stretch", key="graph_back_live"):
            goto("Investigation", selected_case)

        with st.expander("Inspect raw graph payload"):
            st.json(payload)

def ai_investigator() -> None:
    c = get_selected_case()
    case_ids, case_mode, _ = real_case_ids()
    render_provenance_banner("Investigator Decision Support", case_mode, "READ-ONLY", "Only bounded, reviewable investigation outputs are shown.")
    if not case_ids:
        st.error("No live case source is available for AI Investigator.")
        return

    if c["case_id"] not in case_ids and case_ids:
        c = get_selected_case()

    st.markdown(f"""
    <div class="hero compact-hero">
      <div>
        <div class="eyebrow">PHASE 12 • LIVE AGENTIC INVESTIGATION</div>
        <h1>🤖 AI Investigator</h1>
        <p>Run the certified bounded investigation agent against a real GraphShield case ID.</p>
      </div>
      <div class="hero-chip">LIVE /phase12 • Human review required</div>
    </div>
    """, unsafe_allow_html=True)

    tools_ok, tools_payload = api_get("/phase12/tools", timeout=4.0)

    left, right = st.columns([1.55, 1])

    with left:
        selected_case = st.selectbox(
            "Case",
            options=case_ids or [c["case_id"]],
            index=(case_ids.index(c["case_id"]) if c["case_id"] in case_ids else 0),
            key="phase12_case_select",
        )
        st.session_state.selected_case_id = selected_case

        question = st.text_area(
            "Investigation question",
            value=st.session_state.get(
                "phase12_question",
                "Why is this case prioritized, what supporting and countervailing evidence exists, and what policy context should the analyst review?",
            ),
            height=105,
            max_chars=4000,
            key="phase12_question",
        )

        run = st.button(
            "Run bounded investigation →",
            width="stretch",
            type="primary",
            key="phase12_run",
        )

        if run:
            with st.spinner("Running Phase 12 read-only investigation..."):
                ok, payload, status = api_post(
                    "/phase12/investigations",
                    {
                        "case_id": selected_case,
                        "question": question.strip(),
                    },
                    timeout=90.0,
                )
            st.session_state["phase12_last_result"] = {
                "ok": ok,
                "payload": payload,
                "status": status,
            }

        result = st.session_state.get("phase12_last_result")
        if result:
            if result["ok"]:
                st.success("Live Phase 12 investigation completed.")
                payload = result["payload"]

                answer = first_value(
                    payload,
                    "answer",
                    "final_answer",
                    "grounded_answer",
                    "draft",
                    "summary",
                    default=None,
                )
                if answer:
                    st.markdown(
                        f"""
                        <div class="chat-ai">
                          <div class="chat-role ai-role">GraphShield Phase 12</div>
                          <div class="answer-summary">{answer}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                flat = flatten_dict(payload)
                governance_rows = {
                    k: v for k, v in flat.items()
                    if any(word in k.lower() for word in ("human_review", "ground", "withhold", "citation", "mode"))
                }
                if governance_rows:
                    st.markdown('<div class="panel-heading">Grounding & governance</div>', unsafe_allow_html=True)
                    for k, v in list(governance_rows.items())[:12]:
                        st.markdown(
                            f'<div class="evidence-row"><span class="evidence-type">{k.split(".")[-1]}</span><span class="evidence-text">{v}</span></div>',
                            unsafe_allow_html=True,
                        )

                with st.expander("Inspect complete Phase 12 response"):
                    st.json(payload)
            else:
                st.error(
                    f'Phase 12 request failed'
                    + (f' with HTTP {result["status"]}' if result["status"] else '')
                    + '.'
                )
                st.json(result["payload"])

    with right:
        st.markdown('<div class="panel-heading">Certified tool boundary</div>', unsafe_allow_html=True)

        if tools_ok:
            mode = tools_payload.get("mode", "read_only")
            tools = tools_payload.get("tools", [])
            st.markdown(
                f'<div class="mini-stat"><span>Tool mode</span><strong>{mode}</strong></div>',
                unsafe_allow_html=True,
            )
            for tool in tools:
                st.markdown(
                    f"""
                    <div class="tool-row">
                      <div class="tool-num">✓</div>
                      <div><strong>{tool}</strong><span>Certified allowlisted investigation tool</span></div>
                      <div class="tool-readonly">READ ONLY</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.error("Could not read /phase12/tools.")
            st.json(tools_payload)

        st.markdown('<div class="panel-heading">Safety boundaries</div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="safety-card">
              <div>✓ Human analyst review required</div>
              <div>✓ No arbitrary shell/Python/database-write tools</div>
              <div>✓ No autonomous account blocking</div>
              <div>✓ No autonomous case closure</div>
              <div>✓ No SAR/STR filing or regulatory submission</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption(f"Case source: {case_mode}")

        if st.button("💡 Open Explainability", width="stretch", key="ai_explain"):
            goto("Explainability", selected_case)

        if st.button("← Back to Investigation", width="stretch", key="ai_back_live"):
            goto("Investigation", selected_case)


def explainability_page() -> None:
    c = get_selected_case()
    case_ids, case_mode, _ = real_case_ids()
    render_provenance_banner("Model / Detection Intelligence", case_mode, "READ-ONLY", "Model explanation context is recorded separately from case facts.")
    if not case_ids:
        st.error("No live case source is available for Explainability.")
        return

    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">PHASE 11 • LIVE EXPLAINABILITY</div>
            <h1>💡 Explainability</h1>
            <p>Read the certified case explanation bundle without exposing ground-truth labels.</p>
          </div>
          <div class="hero-chip">TreeSHAP graph model • Read only</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_case = st.selectbox(
        "Case",
        options=case_ids or [c["case_id"]],
        index=(case_ids.index(c["case_id"]) if c["case_id"] in case_ids else 0),
        key="phase11_case_select",
    )
    st.session_state.selected_case_id = selected_case

    top_k = st.slider("Top explanation items", 1, 10, 3, 1)

    if st.button("Load live explanation", type="primary", width="stretch", key="load_phase11"):
        ok, payload = api_get(
            f"/explainability/cases/{selected_case}?top_k={top_k}",
            timeout=30.0,
        )
        st.session_state["phase11_last_result"] = {"ok": ok, "payload": payload}

    result = st.session_state.get("phase11_last_result")

    if not result:
        st.info("Choose a real case and click **Load live explanation**.")
        return

    if not result["ok"]:
        st.error("The Phase 11 case explanation endpoint did not return a successful response.")
        st.json(result["payload"])
        return

    payload = result["payload"]
    st.success("Live Phase 11 explanation loaded.")

    schema_version = payload.get("schema_version", "phase11")
    governance = payload.get("governance", {}) if isinstance(payload, dict) else {}

    c1, c2, c3, c4 = st.columns(4)
    cards = [
        ("Schema", schema_version),
        ("Case", payload.get("case_id", selected_case)),
        ("Mode", governance.get("mode", "decision support")),
        ("Human review", bool_label(governance.get("human_review_required", True))),
    ]
    for col, (label, value) in zip((c1, c2, c3, c4), cards):
        with col:
            st.markdown(
                f'<div class="mini-stat"><span>{label}</span><strong>{value}</strong></div>',
                unsafe_allow_html=True,
            )

    flat = flatten_dict(payload)

    st.markdown('<div class="panel-heading">Explanation signals</div>', unsafe_allow_html=True)
    interesting = []
    for key, value in flat.items():
        lk = key.lower()
        if any(
            token in lk
            for token in (
                "reason", "shap", "driver", "feature", "graph",
                "temporal", "fusion", "risk", "score", "summary"
            )
        ):
            if not isinstance(value, (dict, list)):
                interesting.append((key, value))

    if interesting:
        for key, value in interesting[:30]:
            st.markdown(
                f"""
                <div class="evidence-row">
                  <span class="evidence-type">{key.split(".")[-1]}</span>
                  <span class="evidence-text">{value}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("The response structure is available below; no simple scalar explanation fields were detected.")

    st.markdown(
        """
        <div class="safety-card" style="margin-top:1rem">
          <div>✓ TreeSHAP applies only to the frozen LightGBM graph model</div>
          <div>✓ Temporal/TGN context is not falsely presented as SHAP</div>
          <div>✓ Observed reason codes remain separate from model attribution</div>
          <div>✓ Ground-truth / target labels are not exposed to the analyst UI</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Inspect complete Phase 11 response"):
        st.json(payload)

    st.caption(f"Case source: {case_mode}")



def policy_rag_page() -> None:
    c = get_selected_case()
    case_ids, case_mode, _ = real_case_ids()
    render_provenance_banner("Policy / Regulatory Evidence", case_mode, "READ-ONLY", "Policy references support analyst review and do not replace regulatory judgment.")
    if not case_ids:
        st.error("No live case source is available for Policy RAG.")
        return
    selected_default = c["case_id"] if c["case_id"] in case_ids else (case_ids[0] if case_ids else c["case_id"])

    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">PHASE 6 + PHASE 12 • POLICY-GROUNDED REVIEW</div>
            <h1>📚 Policy RAG</h1>
            <p>Retrieve authoritative policy context through the certified bounded investigation workflow and preserve citations for analyst review.</p>
          </div>
          <div class="hero-chip">LIVE Phase 12 • Grounded context only</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_case = st.selectbox(
        "Case",
        options=case_ids or [selected_default],
        index=(case_ids.index(selected_default) if selected_default in case_ids else 0),
        key="policy_case_select",
    )
    st.session_state.selected_case_id = selected_case

    question = st.text_area(
        "Policy question",
        value=st.session_state.get(
            "policy_question",
            "What authoritative AML/KYC policy context is relevant to this case? "
            "Separate case facts from policy guidance, include countervailing context, "
            "and cite the retrieved policy sources.",
        ),
        height=120,
        max_chars=4000,
        key="policy_question",
    )

    if st.button("Retrieve grounded policy context →", type="primary", width="stretch", key="run_policy_rag"):
        with st.spinner("Running bounded policy-grounded investigation..."):
            ok, payload, status = api_post(
                "/phase12/investigations",
                {"case_id": selected_case, "question": question.strip()},
                timeout=90.0,
            )
        st.session_state["policy_last_result"] = {
            "case_id": selected_case,
            "ok": ok,
            "payload": payload,
            "status": status,
        }

    result = st.session_state.get("policy_last_result")
    if not result or result.get("case_id") != selected_case:
        st.info("Choose a case and ask a policy question.")
        st.caption(f"Case source: {case_mode}")
        return

    if not result["ok"]:
        st.error(
            "Policy-grounded investigation failed"
            + (f' with HTTP {result["status"]}' if result.get("status") else "")
            + "."
        )
        st.json(result["payload"])
        return

    payload = result["payload"]
    st.success("Live policy-grounded investigation completed.")

    answer = first_value(
        payload,
        "answer", "final_answer", "grounded_answer", "draft", "summary",
        default=None,
    )
    if answer:
        st.markdown(
            f"""
            <div class="chat-ai">
              <div class="chat-role ai-role">GraphShield grounded policy response</div>
              <div class="answer-summary">{escape(str(answer))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    flat = flatten_dict(payload)
    policy_items = []
    for key, value in flat.items():
        lk = key.lower()
        if any(token in lk for token in ("policy", "citation", "source", "reference", "ground")):
            policy_items.append((key, value))

    st.markdown('<div class="panel-heading">Policy / citation evidence</div>', unsafe_allow_html=True)
    if policy_items:
        for key, value in policy_items[:40]:
            st.markdown(
                f"""
                <div class="evidence-row">
                  <span class="evidence-type">{escape(key.split(".")[-1])}</span>
                  <span class="evidence-text">{escape(str(value))}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("No simple policy/citation scalar fields were detected; inspect the complete response below.")

    st.markdown(
        """
        <div class="safety-card" style="margin-top:1rem">
          <div>✓ Retrieved policy is reference context, not a regulatory decision</div>
          <div>✓ Case facts and policy guidance must remain distinguishable</div>
          <div>✓ Unsupported claims should be withheld by the grounding layer</div>
          <div>✓ Human interpretation and disposition remain mandatory</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Inspect complete grounded response"):
        st.json(payload)

def backend_discovery_page(name: str, icon: str, title: str, subtitle: str, keywords):
    st.markdown(
        f"""
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">LIVE BACKEND DISCOVERY</div>
            <h1>{icon} {title}</h1>
            <p>{subtitle}</p>
          </div>
          <div class="hero-chip">OpenAPI route discovery enabled</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    routes = discover_routes(*keywords)
    if routes:
        st.success(f"Found {len(routes)} matching GraphShield API route(s).")
        for path, methods in routes:
            st.markdown(
                f"""
                <div class="route-card">
                  <div class="route-method">{methods}</div>
                  <div class="route-path">{path}</div>
                  <div class="route-state">DISCOVERED</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.info(
            "Batch 4 discovers the real route names without making unsafe assumptions about request schemas. "
            "The next mapping step can bind the screen to these exact endpoints."
        )
    else:
        st.warning(
            "No matching route was discovered from /openapi.json. "
            "The page remains UI-only until a compatible backend endpoint is available."
        )

def governance_page() -> None:
    render_provenance_banner("Provenance / Audit", "BACKEND_API", "LIVE", "Audit and governance state is read-only and not an autonomous action trigger.")
    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">PHASE 13 • LIVE GOVERNANCE</div>
            <h1>🛡️ Governance & MLOps</h1>
            <p>Read live drift, performance-monitoring and governance-gate state from the GraphShield API.</p>
          </div>
          <div class="hero-chip">LIVE API • Read only</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    endpoints = [
        ("Governance Status", "/phase13/status"),
        ("Drift Monitor", "/phase13/drift"),
        ("Performance Monitor", "/phase13/performance"),
        ("Retraining Proposal", "/phase13/retraining-proposal"),
        ("Governance Gate", "/phase13/governance-gate"),
    ]

    results = []
    for title, path in endpoints:
        ok, payload = api_get(path, timeout=4.0)
        results.append((title, path, ok, payload))

    live_count = sum(1 for _, _, ok, _ in results if ok)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="mini-stat"><span>Live endpoints</span><strong>{live_count}/5</strong></div>', unsafe_allow_html=True)
    with c2:
        status_payload = results[0][3] if results[0][2] else {}
        human = first_value(status_payload, "human_review_required", "human_review", default="Required")
        st.markdown(f'<div class="mini-stat"><span>Human review</span><strong>{bool_label(human)}</strong></div>', unsafe_allow_html=True)
    with c3:
        gate_payload = results[-1][3] if results[-1][2] else {}
        auto = first_value(gate_payload, "automatic_retraining", "auto_retraining", default=False)
        st.markdown(f'<div class="mini-stat"><span>Auto retraining</span><strong>{bool_label(auto)}</strong></div>', unsafe_allow_html=True)
    with c4:
        proposal_payload = results[3][3] if results[3][2] else {}
        proposal = first_value(proposal_payload, "status", "proposal_status", "state", default="Check live")
        st.markdown(f'<div class="mini-stat"><span>Retraining proposal</span><strong>{proposal}</strong></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel-heading">Live governance services</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for idx, (title, path, ok, payload) in enumerate(results):
        with cols[idx % 2]:
            endpoint_status_card(title, path, ok, payload)

    st.markdown('<div class="panel-heading">Governance boundaries</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="safety-card">
          <div>✓ Certified models remain read-only</div>
          <div>✓ No automatic retraining or recalibration</div>
          <div>✓ No automatic model promotion or threshold changes</div>
          <div>✓ Drift signals trigger human investigation, not autonomous action</div>
          <div>✓ Analyst feedback is not silently treated as ground truth</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Inspect live API payloads"):
        for title, path, ok, payload in results:
            st.markdown(f"**{title} — `{path}`**")
            if ok:
                st.json(payload)
            else:
                st.error(payload)

def deployment_page() -> None:
    render_provenance_banner("System / Research Status", "BACKEND_API", "READ-ONLY", "Deployment and readiness checks are informational only.")
    st.markdown(
        """
        <div class="hero compact-hero">
          <div>
            <div class="eyebrow">PHASE 14–15 • LIVE PLATFORM STATUS</div>
            <h1>🚀 Deployment & Reliability</h1>
            <p>Check liveness, readiness, deployment metadata and certified-artifact integrity directly from the running API.</p>
          </div>
          <div class="hero-chip">LIVE API • No deployment actions</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    endpoints = [
        ("Liveness", "/live"),
        ("Readiness", "/ready"),
        ("Deployment", "/deployment"),
        ("Artifact Integrity", "/deployment/integrity"),
    ]

    results = []
    for title, path in endpoints:
        ok, payload = api_get(path, timeout=4.0)
        results.append((title, path, ok, payload))

    c1, c2, c3, c4 = st.columns(4)
    for col, (title, path, ok, payload) in zip((c1,c2,c3,c4), results):
        with col:
            value = "PASS" if ok else "FAIL"
            st.markdown(
                f'<div class="mini-stat"><span>{title}</span><strong>{value}</strong></div>',
                unsafe_allow_html=True,
            )

    st.markdown('<div class="panel-heading">Runtime checks</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for idx, (title, path, ok, payload) in enumerate(results):
        with cols[idx % 2]:
            endpoint_status_card(title, path, ok, payload)

    deployment_payload = results[2][3] if results[2][2] else {}
    integrity_payload = results[3][3] if results[3][2] else {}

    st.markdown('<div class="panel-heading">Release context</div>', unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        release = first_value(deployment_payload, "release", "version", "release_id", default="Runtime metadata")
        env = first_value(deployment_payload, "environment", "env", default="local/dev")
        st.markdown(
            f"""
            <div class="info-live-card">
              <div class="info-live-label">DEPLOYMENT METADATA</div>
              <div class="info-live-value">{release}</div>
              <div class="info-live-copy">Environment: {env}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with b:
        integrity = first_value(integrity_payload, "status", "integrity_status", "result", default="Endpoint responding")
        st.markdown(
            f"""
            <div class="info-live-card">
              <div class="info-live-label">CERTIFIED ARTIFACT INTEGRITY</div>
              <div class="info-live-value">{integrity}</div>
              <div class="info-live-copy">SHA-256 verification is read-only and must fail closed on mismatch.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.info(
        "These checks prove that the local GraphShield API exposes its readiness/integrity contracts. "
        "They do not claim real production SLO attainment or external cloud-network availability."
    )

    with st.expander("Inspect live API payloads"):
        for title, path, ok, payload in results:
            st.markdown(f"**{title} — `{path}`**")
            if ok:
                st.json(payload)
            else:
                st.error(payload)


def transaction_intelligence_view() -> None:
    rows, source_mode, _ = case_catalog()
    render_provenance_banner("Transaction Intelligence", source_mode, "READ-ONLY", "Transaction-level context is derived from the current case queue or backend read-only contract.")
    if not rows:
        st.warning("No case data is available for transaction intelligence.")
        return
    table = []
    for row in rows[:25]:
        table.append(
            {
                "Case": row.get("case_id", "—"),
                "Transaction": row.get("transaction_id", "—"),
                "Entity": row.get("entity", "—"),
                "Risk": row.get("risk_score", "—"),
                "Source": source_mode,
            }
        )
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)


def entity_intelligence_view() -> None:
    rows, source_mode, _ = case_catalog()
    render_provenance_banner("Entity / Counterparty Intelligence", source_mode, "READ-ONLY", "Entity context is limited to connected queue metadata and graph evidence available in the repository.")
    if not rows:
        st.warning("No entity metadata is currently available from the case source.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df[["case_id", "entity", "transaction_id", "risk_score"]].head(25), use_container_width=True, hide_index=True)


def suspicious_network_view() -> None:
    render_provenance_banner("Suspicious Network Detection", "BACKEND_API", "READ-ONLY", "Graph context is evidence-only; it is not a legal determination or confirmed suspicious network finding.")
    st.info("This view reuses the existing point-in-time graph explorer and flagging context from the repository. It does not introduce new detection logic.")
    graph_explorer()


def path_evidence_view() -> None:
    render_provenance_banner("Path / Evidence Explorer", "BACKEND_API", "READ-ONLY", "Evidence is separated into factual graph evidence, interpretation, policy context, and generated explanation.")
    st.caption("FACTUAL TRANSACTION / GRAPH EVIDENCE")
    graph_explorer()
    st.caption("MODEL OR GRAPH INTERPRETATION")
    explainability_page()
    st.caption("POLICY REFERENCE MATERIAL")
    policy_rag_page()


def model_detection_view() -> None:
    render_provenance_banner("Model / Detection Intelligence", "BACKEND_API", "READ-ONLY", "This page reflects the known model lineage history rather than claiming a single production model stack.")
    st.markdown(
        """
        <div class="safety-card">
          <div>✓ Known lineage includes older CatBoost and graph LightGBM artifacts.</div>
          <div>✓ Temporal/TGN components are tracked separately from model explanation outputs.</div>
          <div>✓ Fusion and calibration states remain visible rather than hidden.</div>
          <div>✓ Analyst review remains required for any model-based conclusion.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    explainability_page()


def provenance_audit_view() -> None:
    render_provenance_banner("Provenance / Audit", "BACKEND_API", "READ-ONLY", "Audit metadata, governance status, and case provenance are shown separately from analyst feedback.")
    governance_page()


load_css()
api_ok,_=api_get("/live")
page=sidebar()
topbar(api_ok)

page_aliases = {
    "AML Mission Control": "command_center",
    "Command Center": "command_center",
    "Case Queue": "case_queue",
    "Transaction Intelligence": "transaction_intelligence_view",
    "Entity / Counterparty Intelligence": "entity_intelligence_view",
    "Graph Explorer": "graph_explorer",
    "Suspicious Network Detection": "suspicious_network_view",
    "Risk / Alert Intelligence": "case_queue",
    "Case Investigation": "investigation",
    "Investigation": "investigation",
    "Path / Evidence Explorer": "path_evidence_view",
    "Policy / Regulatory Evidence": "policy_rag_page",
    "Policy RAG": "policy_rag_page",
    "Model / Detection Intelligence": "model_detection_view",
    "Explainability": "explainability_page",
    "Investigator Decision Support": "ai_investigator",
    "AI Investigator": "ai_investigator",
    "Provenance / Audit": "provenance_audit_view",
    "Governance": "governance_page",
    "System / Research Status": "deployment_page",
    "Deployment": "deployment_page",
}

page_name = page_aliases.get(page, "command_center")

if page_name == "command_center":
    command_center(api_ok)
elif page_name == "case_queue":
    case_queue()
elif page_name == "investigation":
    investigation()
elif page_name == "graph_explorer":
    graph_explorer()
elif page_name == "ai_investigator":
    ai_investigator()
elif page_name == "explainability_page":
    explainability_page()
elif page_name == "policy_rag_page":
    policy_rag_page()
elif page_name == "governance_page":
    governance_page()
elif page_name == "deployment_page":
    deployment_page()
elif page_name == "transaction_intelligence_view":
    transaction_intelligence_view()
elif page_name == "entity_intelligence_view":
    entity_intelligence_view()
elif page_name == "suspicious_network_view":
    suspicious_network_view()
elif page_name == "path_evidence_view":
    path_evidence_view()
elif page_name == "model_detection_view":
    model_detection_view()
elif page_name == "provenance_audit_view":
    provenance_audit_view()
else:
    st.error("Unknown UI page.")

st.markdown("""
<div class="footer-note">
GraphShield AML is decision-support software. Analyst review is required. No autonomous blocking, case closure or regulatory filing.
</div>""",unsafe_allow_html=True)
