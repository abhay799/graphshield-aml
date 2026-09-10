from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

SRC_PATH = (
    PROJECT_ROOT
    / "src"
)

if str(SRC_PATH) not in sys.path:

    sys.path.insert(
        0,
        str(SRC_PATH),
    )


from workbench.graph_view import (  # noqa: E402
    render_case_graph_html,
)


from workbench.api_client import (  # noqa: E402
    GraphShieldAPIClient,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title=
        "GraphShield AML Analyst Workbench",

    page_icon="🛡️",

    layout="wide",

    initial_sidebar_state=
        "expanded",
)


API_URL = os.getenv(
    "GRAPHSHIELD_API_URL",
    "http://127.0.0.1:8000",
)


REVIEW_STATUSES = [
    "unreviewed",
    "in_review",
    "needs_more_information",
    "escalated",
    "review_complete",
]


STATUS_LABELS = {
    "unreviewed":
        "Unreviewed",

    "in_review":
        "In Review",

    "needs_more_information":
        "Needs More Information",

    "escalated":
        "Escalated",

    "review_complete":
        "Review Complete",
}


@st.cache_resource
def get_client():

    return GraphShieldAPIClient(
        base_url=API_URL
    )


client = get_client()


# ============================================================
# HEADER
# ============================================================

st.title(
    "🛡️ GraphShield AML"
)

st.caption(
    "Graph-native alert prioritization, "
    "evidence-grounded investigation and "
    "human-reviewed AML decision support"
)


# ============================================================
# HEALTH CHECK
# ============================================================

try:

    health = client.health()

except Exception as error:

    st.error(
        "GraphShield API is not running "
        "or is using an older Phase 7 process."
    )

    st.code(
        (
            ".\\.venv\\Scripts\\python.exe "
            "-m uvicorn api.app:app "
            "--app-dir src "
            "--host 127.0.0.1 "
            "--port 8000"
        )
    )

    st.exception(
        error
    )

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "System Status"
    )

    st.success(
        "API Online"
    )

    st.metric(
        "Analyst Queue",
        f"{health.get('case_queue_rows', 0):,}",
    )

    st.metric(
        "Champion",
        health.get(
            "champion",
            "Unknown",
        ),
    )

    st.caption(
        "Certified Phase 1–6 artifacts "
        "remain read-only."
    )

    st.divider()

    st.header(
        "Queue Controls"
    )

    page_size = st.selectbox(
        "Cases per page",
        options=[
            25,
            50,
            100,
            250,
        ],
        index=1,
    )

    page_number = st.number_input(
        "Page",
        min_value=1,
        value=1,
        step=1,
    )


offset = (
    int(page_number) - 1
) * int(page_size)


# ============================================================
# LOAD QUEUE
# ============================================================

try:

    queue_payload = (
        client.list_cases(
            limit=int(
                page_size
            ),
            offset=offset,
        )
    )

    cases = queue_payload[
        "cases"
    ]

except Exception as error:

    st.error(
        "Unable to load case queue."
    )

    st.exception(
        error
    )

    st.stop()


if not cases:

    st.warning(
        "No cases are available "
        "on this queue page."
    )

    st.stop()


case_ids = [
    case["case_id"]
    for case in cases
]


# ============================================================
# SHARED CASE SELECTOR
# ============================================================

selected_case = st.selectbox(
    "Selected investigation case",
    options=case_ids,
    index=0,
)


# ============================================================
# TABS
# ============================================================

(
    queue_tab,
    investigation_tab,
    graph_tab,
    workflow_tab,
    evidence_tab,
    policy_tab,
    governance_tab,
) = st.tabs(
    [
        "📋 Case Queue",
        "🔎 Investigation",
        "🕸️ Transaction Graph",
        "📝 Analyst Workflow",
        "📚 Evidence Search",
        "⚖️ Policy Search",
        "🔐 Governance",
    ]
)


# ============================================================
# CASE QUEUE
# ============================================================

with queue_tab:

    st.subheader(
        "Prioritized Analyst Queue"
    )

    st.caption(
        "Cases are ranked by the frozen "
        "lightgbm_graph champion."
    )

    queue_df = pd.DataFrame(
        cases
    )

    preferred_columns = [
        "risk_rank",
        "case_id",
        "risk_score",
        "transaction_id",
        "is_laundering",
        "source_model",
    ]

    visible_columns = [
        column
        for column
        in preferred_columns
        if column
        in queue_df.columns
    ]

    remaining_columns = [
        column
        for column
        in queue_df.columns
        if column
        not in visible_columns
    ]

    display_df = queue_df[
        visible_columns
        + remaining_columns
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        (
            f"Showing queue rows "
            f"{offset + 1:,}–"
            f"{offset + len(cases):,}"
        )
    )


# ============================================================
# INVESTIGATION
# ============================================================

with investigation_tab:

    st.subheader(
        f"Investigation — {selected_case}"
    )

    col1, col2 = st.columns(
        2
    )

    try:

        case = client.get_case(
            selected_case
        )

        with col1:

            st.markdown(
                "#### Case Metadata"
            )

            st.json(
                case
            )


        with col2:

            risk_rank = case.get(
                "risk_rank"
            )

            risk_score = case.get(
                "risk_score"
            )

            if risk_rank is not None:

                st.metric(
                    "Risk Rank",
                    risk_rank,
                )

            if risk_score is not None:

                try:

                    st.metric(
                        "Risk Score",
                        f"{float(risk_score):.6f}",
                    )

                except Exception:

                    st.metric(
                        "Risk Score",
                        risk_score,
                    )

            st.info(
                "Analyst decision support only. "
                "No automatic account blocking, "
                "case closure or regulatory filing."
            )

    except Exception as error:

        st.exception(
            error
        )


    st.divider()

    if st.button(
        "Load Investigation Snapshot",
        type="primary",
    ):

        with st.spinner(
            "Loading case evidence..."
        ):

            try:

                snapshot = (
                    client.snapshot(
                        selected_case
                    )
                )

                (
                    overview_section,
                    paths_section,
                    history_section,
                ) = st.tabs(
                    [
                        "Overview",
                        "Paths",
                        "History",
                    ]
                )

                with overview_section:

                    st.json(
                        snapshot.get(
                            "overview"
                        )
                    )

                with paths_section:

                    st.json(
                        snapshot.get(
                            "paths"
                        )
                    )

                with history_section:

                    st.json(
                        snapshot.get(
                            "history"
                        )
                    )

            except Exception as error:

                st.exception(
                    error
                )


# ============================================================
# CASE TRANSACTION GRAPH
# ============================================================

with graph_tab:

    st.subheader(
        f"Transaction Network - {selected_case}"
    )

    st.caption(
        "Interactive read-only visualization of the "
        "materialized point-in-time case subgraph."
    )


    graph_edge_limit = st.slider(
        "Maximum displayed transactions",
        min_value=25,
        max_value=500,
        value=200,
        step=25,
        key="graph_edge_limit",
    )


    if st.button(
        "Load Transaction Graph",
        key="load_transaction_graph",
    ):

        with st.spinner(
            "Building interactive case graph..."
        ):

            try:

                graph_payload = (
                    client.case_graph(
                        case_id=
                            selected_case,

                        max_edges=
                            graph_edge_limit,
                    )
                )


                metric1, metric2, metric3 = (
                    st.columns(
                        3
                    )
                )


                with metric1:

                    st.metric(
                        "Displayed Accounts",
                        graph_payload.get(
                            "displayed_nodes",
                            0,
                        ),
                    )


                with metric2:

                    st.metric(
                        "Displayed Transactions",
                        graph_payload.get(
                            "displayed_edges",
                            0,
                        ),
                    )


                with metric3:

                    st.metric(
                        "Total Case Edges",
                        graph_payload.get(
                            "total_subgraph_edges",
                            0,
                        ),
                    )


                st.caption(
                    "Diamond nodes are focal-transaction "
                    "endpoints. The thicker edge is the "
                    "focal transaction."
                )


                graph_html = (
                    render_case_graph_html(
                        graph_payload
                    )
                )


                components.html(
                    graph_html,
                    height=750,
                    scrolling=False,
                )


                with st.expander(
                    "Graph metadata"
                ):

                    st.json(
                        {
                            "case_id":
                                graph_payload.get(
                                    "case_id"
                                ),

                            "focal_transaction_id":
                                graph_payload.get(
                                    "focal_transaction_id"
                                ),

                            "risk_rank":
                                graph_payload.get(
                                    "risk_rank"
                                ),

                            "risk_score":
                                graph_payload.get(
                                    "risk_score"
                                ),

                            "source_column":
                                graph_payload.get(
                                    "source_column"
                                ),

                            "target_column":
                                graph_payload.get(
                                    "target_column"
                                ),
                        }
                    )


            except Exception as error:

                message = str(
                    error
                )


                if (
                    "not eagerly materialized"
                    in message.lower()
                ):

                    st.info(
                        "This case is part of the "
                        "7,617-case analyst queue but "
                        "is outside the top-374 eagerly "
                        "materialized investigation set. "
                        "Its graph can be materialized "
                        "on demand later."
                    )

                else:

                    st.exception(
                        error
                    )


# ============================================================
# ANALYST WORKFLOW
# ============================================================

with workflow_tab:

    st.subheader(
        f"Analyst Review — {selected_case}"
    )

    st.caption(
        "Operational analyst state is stored "
        "separately from certified Phase 1–6 artifacts."
    )

    try:

        current_state = (
            client.get_case_state(
                selected_case
            )
        )

    except Exception as error:

        st.error(
            "Unable to load analyst state."
        )

        st.exception(
            error
        )

        current_state = None


    if current_state is not None:

        current_status = (
            current_state.get(
                "review_status",
                "unreviewed",
            )
        )

        if (
            current_status
            not in REVIEW_STATUSES
        ):

            current_status = (
                "unreviewed"
            )


        status_col, actor_col = (
            st.columns(
                2
            )
        )


        with status_col:

            st.metric(
                "Current Status",
                STATUS_LABELS.get(
                    current_status,
                    current_status,
                ),
            )


        with actor_col:

            updated_at = (
                current_state.get(
                    "updated_at_utc"
                )
            )

            if updated_at:

                st.caption(
                    "Last updated"
                )

                st.write(
                    updated_at
                )

            else:

                st.caption(
                    "No analyst review recorded yet."
                )


        st.divider()


        with st.form(
            "analyst_review_form"
        ):

            actor = st.text_input(
                "Analyst",
                value="local_analyst",
                max_chars=128,
            )


            selected_status = (
                st.selectbox(
                    "Review Status",
                    options=
                        REVIEW_STATUSES,

                    index=
                        REVIEW_STATUSES.index(
                            current_status
                        ),

                    format_func=
                        lambda value:
                            STATUS_LABELS[
                                value
                            ],
                )
            )


            existing_note = (
                current_state.get(
                    "analyst_note"
                )
                or ""
            )


            note = st.text_area(
                "Analyst Notes",
                value=existing_note,
                height=180,
                max_chars=5000,
                placeholder=(
                    "Record observations, "
                    "evidence reviewed, rationale "
                    "or required follow-up."
                ),
            )


            submitted = (
                st.form_submit_button(
                    "Save Review State",
                    type="primary",
                )
            )


        if submitted:

            try:

                updated = (
                    client.update_case_state(
                        case_id=
                            selected_case,

                        review_status=
                            selected_status,

                        analyst_note=
                            note or None,

                        actor=
                            actor,
                    )
                )

                st.success(
                    (
                        "Review state saved: "
                        f"{STATUS_LABELS.get(updated['review_status'], updated['review_status'])}"
                    )
                )

                st.rerun()

            except Exception as error:

                st.exception(
                    error
                )


        st.divider()

        st.markdown(
            "#### Audit History"
        )

        audit_limit = st.selectbox(
            "Audit events",
            options=[
                25,
                50,
                100,
                250,
            ],
            index=1,
        )


        try:

            audit_payload = (
                client.audit_history(
                    case_id=
                        selected_case,

                    limit=
                        int(
                            audit_limit
                        ),
                )
            )

            events = (
                audit_payload.get(
                    "events",
                    []
                )
            )


            if not events:

                st.info(
                    "No audit events "
                    "for this case yet."
                )

            else:

                audit_rows = []

                for event in events:

                    audit_rows.append(
                        {
                            "timestamp":
                                event.get(
                                    "event_ts_utc"
                                ),

                            "actor":
                                event.get(
                                    "actor"
                                ),

                            "event_type":
                                event.get(
                                    "event_type"
                                ),

                            "event_id":
                                event.get(
                                    "event_id"
                                ),
                        }
                    )


                st.dataframe(
                    pd.DataFrame(
                        audit_rows
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


                with st.expander(
                    "View complete audit payloads"
                ):

                    st.json(
                        events
                    )

        except Exception as error:

            st.exception(
                error
            )


# ============================================================
# CASE EVIDENCE SEARCH
# ============================================================

with evidence_tab:

    st.subheader(
        "Case Evidence Retrieval"
    )

    st.caption(
        f"Search evidence restricted "
        f"to {selected_case}"
    )


    evidence_query = (
        st.text_input(
            "Evidence question",
            placeholder=(
                "Example: unusual "
                "counterparties, rapid "
                "movement or reciprocal "
                "activity"
            ),
        )
    )


    evidence_top_k = st.slider(
        "Evidence results",
        min_value=1,
        max_value=10,
        value=5,
    )


    if st.button(
        "Search Case Evidence"
    ):

        if not evidence_query.strip():

            st.warning(
                "Enter an evidence query."
            )

        else:

            with st.spinner(
                "Searching certified "
                "case evidence..."
            ):

                try:

                    evidence = (
                        client.search_evidence(
                            case_id=
                                selected_case,

                            query=
                                evidence_query,

                            top_k=
                                evidence_top_k,
                        )
                    )

                    st.json(
                        evidence
                    )

                except Exception as error:

                    st.exception(
                        error
                    )


# ============================================================
# POLICY SEARCH
# ============================================================

with policy_tab:

    st.subheader(
        "Authoritative Policy Retrieval"
    )


    policy_query = st.text_input(
        "Policy question",
        placeholder=(
            "Example: suspicious "
            "transaction monitoring "
            "obligations"
        ),
    )


    policy_col1, policy_col2 = (
        st.columns(
            2
        )
    )


    with policy_col1:

        policy_top_k = (
            st.slider(
                "Policy results",
                min_value=1,
                max_value=10,
                value=5,
            )
        )


    with policy_col2:

        jurisdiction_option = (
            st.selectbox(
                "Jurisdiction filter",
                options=[
                    "All",
                    "India",
                    "United States",
                    "International",
                ],
            )
        )


    jurisdiction = (
        None
        if jurisdiction_option
        == "All"
        else jurisdiction_option
    )


    if st.button(
        "Search Policy Corpus"
    ):

        if not policy_query.strip():

            st.warning(
                "Enter a policy question."
            )

        else:

            with st.spinner(
                "Searching authoritative "
                "policy corpus..."
            ):

                try:

                    policy_results = (
                        client.search_policy(
                            query=
                                policy_query,

                            top_k=
                                policy_top_k,

                            jurisdiction=
                                jurisdiction,
                        )
                    )

                    st.json(
                        policy_results
                    )

                except Exception as error:

                    st.exception(
                        error
                    )


# ============================================================
# GOVERNANCE
# ============================================================

with governance_tab:

    st.subheader(
        "Safety & Governance"
    )

    try:

        governance = (
            client.governance()
        )

        st.json(
            governance
        )

        st.success(
            "GraphShield operates as "
            "analyst decision support."
        )

        st.warning(
            "Human review is required before "
            "account action, case closure or "
            "regulatory filing."
        )

        st.markdown(
            """
**Operational boundaries**

- Risk scores prioritize investigation; they do not determine guilt.
- Analyst review state is stored only in the Phase 7 operational database.
- Phase 1–6 certified model, evidence and policy artifacts remain immutable.
- No autonomous account blocking is exposed.
- No autonomous case closure is exposed.
- No autonomous regulatory filing is exposed.
"""
        )

    except Exception as error:

        st.exception(
            error
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "GraphShield AML • Phase 7 Analyst Workbench • "
    "Human-reviewed decision support • "
    "Frozen Phase 1–6 intelligence artifacts"
)
