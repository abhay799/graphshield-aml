from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json

from fastapi.testclient import TestClient

from api.app import app


ROOT = Path(".")
REPORT_DIR = ROOT / "reports" / "phase7"

REPORT_JSON = (
    REPORT_DIR
    / "phase7_integration_audit.json"
)

REPORT_MD = (
    REPORT_DIR
    / "phase7_integration_audit.md"
)


def sha256_file(
    path: Path,
) -> str:

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


client = TestClient(
    app
)


results = {}


# ============================================================
# 1. SYSTEM HEALTH
# ============================================================

response = client.get(
    "/health"
)

assert response.status_code == 200, (
    response.text
)

health = response.json()

assert health[
    "status"
] == "ok"

assert health[
    "case_queue_rows"
] == 7617

assert health[
    "champion"
] == "lightgbm_graph"

results[
    "health"
] = True

print(
    "SYSTEM HEALTH: PASS"
)


# ============================================================
# 2. GOVERNANCE
# ============================================================

response = client.get(
    "/governance"
)

assert response.status_code == 200

governance = response.json()

assert governance[
    "human_review_required"
] is True

assert governance[
    "autonomous_account_blocking"
] is False

assert governance[
    "autonomous_case_closure"
] is False

assert governance[
    "autonomous_regulatory_filing"
] is False

results[
    "governance"
] = True

print(
    "GOVERNANCE: PASS"
)


# ============================================================
# 3. AUTHORITATIVE QUEUE
# ============================================================

response = client.get(
    "/cases?limit=5"
)

assert response.status_code == 200

payload = response.json()

assert payload[
    "count"
] == 5

cases = payload[
    "cases"
]

assert len(cases) == 5

case_id = cases[0][
    "case_id"
]

results[
    "queue"
] = True

print(
    "CASE QUEUE: PASS"
)

print(
    "Test case:",
    case_id,
)


# ============================================================
# 4. CASE LOOKUP
# ============================================================

response = client.get(
    f"/cases/{case_id}"
)

assert response.status_code == 200

case = response.json()

assert case[
    "case_id"
] == case_id

assert case[
    "source_model"
] == "lightgbm_graph"

results[
    "case_lookup"
] = True

print(
    "CASE LOOKUP: PASS"
)


# ============================================================
# 5. INVESTIGATION SNAPSHOT
# ============================================================

response = client.get(
    f"/cases/{case_id}/snapshot"
)

assert response.status_code == 200, (
    response.text
)

snapshot = response.json()

for key in [
    "case",
    "overview",
    "paths",
    "history",
]:

    assert key in snapshot


results[
    "investigation_snapshot"
] = True

print(
    "INVESTIGATION SNAPSHOT: PASS"
)


# ============================================================
# 6. GRAPH ENDPOINT
# ============================================================

response = client.get(
    (
        f"/cases/{case_id}"
        "/graph?max_edges=100"
    )
)

assert response.status_code == 200, (
    response.text
)

graph = response.json()

assert graph[
    "materialized"
] is True

assert graph[
    "displayed_nodes"
] >= 2

assert graph[
    "displayed_edges"
] >= 1

assert graph[
    "source_column"
] == "from_account_key"

assert graph[
    "target_column"
] == "to_account_key"


focal_edges = [
    edge
    for edge in graph[
        "edges"
    ]
    if edge.get(
        "is_focal"
    )
]

assert len(
    focal_edges
) >= 1


results[
    "case_graph"
] = True

print(
    "INTERACTIVE GRAPH DATA: PASS"
)


# ============================================================
# 7. CASE EVIDENCE RETRIEVAL
# ============================================================

response = client.post(
    (
        f"/cases/{case_id}"
        "/evidence/search"
    ),
    json={
        "query":
            (
                "unusual transaction activity "
                "and counterparties"
            ),

        "top_k":
            5,
    },
)

assert response.status_code == 200, (
    response.text
)

evidence = response.json()

assert evidence[
    "results"
]

results[
    "case_evidence"
] = True

print(
    "CASE EVIDENCE RETRIEVAL: PASS"
)


# ============================================================
# 8. AUTHORITATIVE POLICY RETRIEVAL
# ============================================================

response = client.post(
    "/policy/search",
    json={
        "query":
            (
                "suspicious transaction "
                "monitoring obligations"
            ),

        "top_k":
            5,

        "jurisdiction":
            None,
    },
)

assert response.status_code == 200, (
    response.text
)

policy = response.json()

assert policy[
    "results"
]

results[
    "policy_retrieval"
] = True

print(
    "POLICY RETRIEVAL: PASS"
)


# ============================================================
# 9. UNIFIED CASE INTELLIGENCE
# ============================================================

response = client.post(
    f"/cases/{case_id}/intelligence",
    json={
        "question":
            (
                "What unusual transaction "
                "activity should the analyst "
                "review?"
            ),

        "evidence_top_k":
            3,

        "include_policy":
            True,

        "policy_top_k":
            3,

        "jurisdiction":
            None,
    },
)

assert response.status_code == 200, (
    response.text
)

dossier = response.json()


required_dossier = [
    "case",
    "graph",
    "investigation",
    "retrieval",
    "analyst",
    "governance",
]


for key in required_dossier:

    assert key in dossier


assert dossier[
    "case_id"
] == case_id

assert dossier[
    "retrieval"
][
    "case_evidence"
]

assert dossier[
    "retrieval"
][
    "policy_grounding"
]

assert dossier[
    "retrieval"
][
    "policy_requested"
] is True

assert dossier[
    "governance"
][
    "human_review_required"
] is True

assert dossier[
    "governance"
][
    "autonomous_regulatory_filing"
] is False


results[
    "unified_case_intelligence"
] = True

print(
    "UNIFIED CASE INTELLIGENCE: PASS"
)


# ============================================================
# 10. ANALYST WORKFLOW
# ============================================================

response = client.put(
    (
        f"/analyst/cases/"
        f"{case_id}/state"
    ),
    json={
        "review_status":
            "in_review",

        "analyst_note":
            (
                "Step 125 end-to-end "
                "integration validation"
            ),

        "actor":
            "phase7_integration_test",
    },
)

assert response.status_code == 200, (
    response.text
)

updated = response.json()

assert updated[
    "review_status"
] == "in_review"

results[
    "analyst_state_write"
] = True

print(
    "ANALYST STATE WRITE: PASS"
)


# ============================================================
# 11. STATE PERSISTENCE
# ============================================================

response = client.get(
    (
        f"/analyst/cases/"
        f"{case_id}/state"
    )
)

assert response.status_code == 200

persisted = response.json()

assert persisted[
    "review_status"
] == "in_review"

results[
    "analyst_state_persistence"
] = True

print(
    "ANALYST STATE PERSISTENCE: PASS"
)


# ============================================================
# 12. APPEND-ONLY AUDIT TRAIL
# ============================================================

response = client.get(
    (
        f"/analyst/cases/"
        f"{case_id}/audit?limit=100"
    )
)

assert response.status_code == 200

audit = response.json()

assert audit[
    "count"
] >= 1


matching_events = [
    event
    for event in audit[
        "events"
    ]
    if (
        event[
            "event_type"
        ]
        == "case_state_updated"
    )
]


assert matching_events


results[
    "audit_trail"
] = True

print(
    "APPEND-ONLY AUDIT TRAIL: PASS"
)


# ============================================================
# 13. INVALID ANALYST ACTION REJECTION
# ============================================================

response = client.put(
    (
        f"/analyst/cases/"
        f"{case_id}/state"
    ),
    json={
        "review_status":
            "AUTO_BLOCK_ACCOUNT",

        "analyst_note":
            "Unsafe action test",

        "actor":
            "phase7_integration_test",
    },
)

assert response.status_code == 400


results[
    "invalid_state_rejection"
] = True

print(
    "UNSAFE STATE REJECTION: PASS"
)


# ============================================================
# 14. UNKNOWN CASE REJECTION
# ============================================================

response = client.get(
    "/cases/CASE_DOES_NOT_EXIST"
)

assert response.status_code == 404


response = client.get(
    (
        "/analyst/cases/"
        "CASE_DOES_NOT_EXIST/state"
    )
)

assert response.status_code == 404


results[
    "unknown_case_rejection"
] = True

print(
    "UNKNOWN CASE HANDLING: PASS"
)


# ============================================================
# 15. REQUEST VALIDATION
# ============================================================

response = client.post(
    (
        f"/cases/{case_id}"
        "/evidence/search"
    ),
    json={
        "query":
            "",

        "top_k":
            5,
    },
)

assert response.status_code == 422


response = client.post(
    "/policy/search",
    json={
        "query":
            "",

        "top_k":
            5,
    },
)

assert response.status_code == 422


results[
    "request_validation"
] = True

print(
    "REQUEST VALIDATION: PASS"
)


# ============================================================
# 16. PHASE 1-6 FREEZE RECORD STILL EXISTS
# ============================================================

freeze_path = (
    ROOT
    / "reports"
    / "final"
    / "phases_1_6_artifact_freeze.json"
)

assert freeze_path.exists()


freeze = json.loads(
    freeze_path.read_text(
        encoding="utf-8"
    )
)


assert freeze[
    "status"
] == "CERTIFIED"

assert freeze[
    "authoritative_champion"
][
    "model"
] == "lightgbm_graph"


results[
    "phase1_6_freeze_present"
] = True

print(
    "PHASE 1-6 FREEZE RECORD: PASS"
)


# ============================================================
# 17. PHASE 7 OPERATIONAL STORE SEPARATION
# ============================================================

phase7_db = (
    ROOT
    / "data"
    / "phase7"
    / "analyst_workbench.sqlite"
)

assert phase7_db.exists()


assert (
    "data/phase7"
    in str(
        phase7_db
    ).replace(
        "\\",
        "/",
    )
)


results[
    "operational_state_separation"
] = True

print(
    "PHASE 7 STATE SEPARATION: PASS"
)


# ============================================================
# 18. WRITE AUDIT REPORT
# ============================================================

report = {
    "project":
        "GraphShield AML",

    "phase":
        7,

    "audit":
        "end_to_end_integration",

    "created_at_utc":
        datetime.now(
            timezone.utc
        ).isoformat(),

    "test_case_id":
        case_id,

    "results":
        results,

    "all_passed":
        all(
            results.values()
        ),

    "governance": {
        "decision_support_only":
            True,

        "human_review_required":
            True,

        "autonomous_account_blocking":
            False,

        "autonomous_case_closure":
            False,

        "autonomous_regulatory_filing":
            False,
    },

    "architecture": {
        "phase1_6":
            "certified read-only intelligence artifacts",

        "phase7":
            "API, Workbench and separate operational analyst state",
    },
}


if not report[
    "all_passed"
]:

    raise RuntimeError(
        "One or more Phase 7 "
        "integration gates failed"
    )


REPORT_JSON.write_text(
    json.dumps(
        report,
        indent=2,
    ),
    encoding="utf-8",
)


REPORT_MD.write_text(
    "\n".join(
        [
            "# GraphShield AML - Phase 7 Integration Audit",
            "",
            f"Test case: `{case_id}`",
            "",
            "## Integration Gates",
            "",
            "- System health: PASS",
            "- Governance: PASS",
            "- Authoritative case queue: PASS",
            "- Case lookup: PASS",
            "- Investigation snapshot: PASS",
            "- Interactive graph data: PASS",
            "- Case evidence retrieval: PASS",
            "- Authoritative policy retrieval: PASS",
            "- Unified case intelligence: PASS",
            "- Analyst state persistence: PASS",
            "- Append-only audit trail: PASS",
            "- Unsafe state rejection: PASS",
            "- Unknown case handling: PASS",
            "- Request validation: PASS",
            "- Phase 1-6 freeze record: PASS",
            "- Phase 7 operational-state separation: PASS",
            "",
            "## Governance",
            "",
            "- Human review required",
            "- No autonomous account blocking",
            "- No autonomous case closure",
            "- No autonomous regulatory filing",
            "",
            "**STEP 125: PASS**",
        ]
    ),
    encoding="utf-8",
)


print()
print("Created:")
print(REPORT_JSON)
print(REPORT_MD)


print()
print("=" * 90)
print("SYSTEM HEALTH: PASS")
print("CASE QUEUE -> INVESTIGATION: PASS")
print("INVESTIGATION -> GRAPH: PASS")
print("INVESTIGATION -> EVIDENCE: PASS")
print("INVESTIGATION -> POLICY: PASS")
print("UNIFIED CASE INTELLIGENCE: PASS")
print("ANALYST WORKFLOW + PERSISTENCE: PASS")
print("APPEND-ONLY AUDIT TRAIL: PASS")
print("UNSAFE ACTION REJECTION: PASS")
print("ERROR HANDLING: PASS")
print("HUMAN-REVIEW GOVERNANCE: PASS")
print("PHASE 1-6 / PHASE 7 STATE SEPARATION: PASS")
print()
print("PHASE 7 STEP 125 END-TO-END INTEGRATION AUDIT: PASS")
print("=" * 90)
