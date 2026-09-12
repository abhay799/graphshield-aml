from __future__ import annotations

from investigation.phase12_agent import (
    Phase12InvestigationAgent,
)
from investigation.phase12_contracts import (
    ToolCallResult,
)


EVIDENCE_ID = "EVID_ABCDEF1234567890"


def _fake_tool_result(request):
    return ToolCallResult(
        tool_name=request.tool_name,
        success=True,
        case_id=request.case_id,
        evidence_ids=[EVIDENCE_ID],
        payload=[
            {
                "evidence_id": EVIDENCE_ID,
                "source_type": "synthetic_test_evidence",
                "source_ref": "test://phase12",
                "content": (
                    "The transaction has prior account-pair activity."
                ),
            }
        ],
        error=None,
        latency_ms=0.1,
    )


def test_phase12_agent_withholds_uncited_answer(
    monkeypatch,
    tmp_path,
):
    import investigation.phase12_agent as agent_module

    agent = Phase12InvestigationAgent(
        max_tool_calls=3,
        max_evidence_documents=10,
    )

    monkeypatch.setattr(
        agent.tools,
        "execute",
        _fake_tool_result,
    )

    monkeypatch.setattr(
        agent_module,
        "AUDIT_LOG",
        tmp_path / "audit_chain.jsonl",
    )

    monkeypatch.setattr(
        agent_module,
        "generate_grounded_answer",
        lambda question, documents: {
            "answer": (
                "The transaction has prior account-pair activity."
            ),
            "cited_ids": [],
            "validation_passed": True,
        },
    )

    result = agent.run(
        case_id="CASE_TEST",
        question="Review this case.",
    )

    assert result.status == "completed"
    assert result.answer_withheld is True
    assert result.citation_validation_passed is False
    assert result.grounding_validation["passed"] is False
    assert "withheld" in result.answer.lower()


def test_phase12_agent_releases_strictly_grounded_answer(
    monkeypatch,
    tmp_path,
):
    import investigation.phase12_agent as agent_module

    agent = Phase12InvestigationAgent(
        max_tool_calls=3,
        max_evidence_documents=10,
    )

    monkeypatch.setattr(
        agent.tools,
        "execute",
        _fake_tool_result,
    )

    monkeypatch.setattr(
        agent_module,
        "AUDIT_LOG",
        tmp_path / "audit_chain.jsonl",
    )

    grounded_answer = (
        "The transaction has prior account-pair activity "
        f"[{EVIDENCE_ID}]. "
        "Human analyst review is required."
    )

    monkeypatch.setattr(
        agent_module,
        "generate_grounded_answer",
        lambda question, documents: {
            "answer": grounded_answer,
            "cited_ids": [EVIDENCE_ID],
            "validation_passed": True,
        },
    )

    result = agent.run(
        case_id="CASE_TEST",
        question="Review this case.",
    )

    assert result.status == "completed"
    assert result.answer_withheld is False
    assert result.citation_validation_passed is True
    assert result.grounding_validation["passed"] is True
    assert result.answer == grounded_answer
