from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from app.agents.recommendation_agent import RecommendationAgent
from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult
from app.agents.workflow import create_default_agent_registry
from app.gateways.policy_context import (
    PolicyContextResult,
    PolicyEvidenceCandidate,
)


def risk_result(
    factors: list[dict] | None = None,
    *,
    complete: bool = True,
    status: str = "SUCCESS",
    level: str = "HIGH",
) -> AgentResult:
    return AgentResult(
        agent_name="RiskDetectionAgent",
        route="risk",
        status=status,
        summary="Risk summary",
        data={
            "risk_level": level,
            "risk_factors": factors or [],
            "assessment_complete": complete,
        },
    )


def factor(dimension: str, level: str = "HIGH", **values) -> dict:
    return {
        "dimension": dimension,
        "level": level,
        "reason": f"Confirmed {dimension} concern.",
        "values": values,
        "evidence_source": "risk",
    }


def candidate(**metadata) -> PolicyEvidenceCandidate:
    values = {"source": "Academic Policy", "section": "Tutor guidance"}
    values.update(metadata)
    return PolicyEvidenceCandidate(
        chunk_id="chunk-1",
        text="Tutors should provide early guidance.",
        score=0.92,
        source="Academic Policy",
        metadata=values,
    )


def policy_gateway(result: PolicyContextResult | None = None) -> Mock:
    gateway = Mock()
    gateway.retrieve_policy = AsyncMock(
        return_value=result
        or PolicyContextResult(query="query", candidates=(candidate(),))
    )
    return gateway


def state_with(
    risk: AgentResult | None,
    *,
    selected: list[str] | None = None,
    completed: list[str] | None = None,
    supporting: bool = True,
) -> AgentState:
    state = create_initial_state(user_message="Recommend actions", student_id=42)
    state.selected_agents = selected or ["risk", "recommendation"]
    state.completed_agents = completed if completed is not None else ["risk"]
    if risk is not None:
        state.agent_results["risk"] = risk
    if supporting:
        state.agent_results["progress"] = AgentResult(
            "ProgressAnalysisAgent", "progress", "SUCCESS", "Progress", {"completed_ects": 60}
        )
        state.agent_results["study_rights"] = AgentResult(
            "StudyRightsAgent", "study_rights", "SUCCESS", "Study right", {"status": "ACTIVE"}
        )
    return state


def run(agent: RecommendationAgent, state: AgentState) -> AgentResult:
    return asyncio.run(agent.run(state))


def make_agent(policy: Mock) -> RecommendationAgent:
    return RecommendationAgent(Mock(), policy)


def test_high_progress_factor_produces_two_actionable_recommendations():
    policy = policy_gateway()
    result = run(
        make_agent(policy),
        state_with(risk_result([factor("progress", "HIGH", ects_deficit=70)])),
    )

    actions = [item["action"] for item in result.data["recommendations"]]
    assert actions == ["Review the student's study plan.", "Schedule a tutor meeting."]
    assert all(item["priority"] == "HIGH" for item in result.data["recommendations"])
    assert result.status == "SUCCESS"
    policy.retrieve_policy.assert_awaited_once_with(
        "academic progress deficit tutor support policy", top_k=3
    )


def test_low_progress_factor_does_not_schedule_meeting_or_recalculate_risk():
    result = run(
        make_agent(policy_gateway()),
        state_with(risk_result([factor("progress", "LOW", ects_deficit=1)], level="LOW")),
    )

    recommendations = result.data["recommendations"]
    assert [item["action"] for item in recommendations] == [
        "Review the student's study plan."
    ]
    assert recommendations[0]["student_evidence"][0]["values"]["ects_deficit"] == 1


def test_study_right_factor_uses_authoritative_priority_and_supporting_agent():
    result = run(
        make_agent(policy_gateway()),
        state_with(risk_result([factor("study_right", "HIGH", status="EXPIRED")])),
    )

    recommendation = result.data["recommendations"][0]
    assert recommendation["action"] == "Check study-right extension/support options."
    assert recommendation["priority"] == "HIGH"
    assert recommendation["source_agents"] == ["risk", "study_rights"]


def test_deadline_factor_produces_approved_advisory_action():
    result = run(
        make_agent(policy_gateway()),
        state_with(risk_result([factor("academic_event", "MEDIUM", days_until_event=5)])),
    )

    recommendation = result.data["recommendations"][0]
    assert recommendation["category"] == "deadline"
    assert "agree on the required next step" in recommendation["action"]


def test_multiple_factors_preserve_priority_and_run_narrow_queries():
    policy = policy_gateway()
    factors = [
        factor("progress", "HIGH", ects_deficit=70),
        factor("study_right", "MEDIUM", status="EXPIRES_SOON"),
        factor("academic_event", "MEDIUM", days_until_event=2),
    ]
    result = run(make_agent(policy), state_with(risk_result(factors)))

    assert [item["priority"] for item in result.data["recommendations"]] == [
        "HIGH", "HIGH", "MEDIUM", "MEDIUM"
    ]
    assert policy.retrieve_policy.await_count == 3
    queries = [call.args[0] for call in policy.retrieve_policy.await_args_list]
    assert queries == [
        "academic progress deficit tutor support policy",
        "expiring study right extension support policy",
        "upcoming academic deadline tutor guidance",
    ]


def test_policy_evidence_preserves_identifier_score_source_and_metadata():
    result = run(
        make_agent(policy_gateway()),
        state_with(risk_result([factor("progress", "MEDIUM")])),
    )

    evidence = result.data["recommendations"][0]["policy_evidence"][0]
    assert evidence == {
        "chunk_id": "chunk-1",
        "score": 0.92,
        "source": "Academic Policy",
        "metadata": {"source": "Academic Policy", "section": "Tutor guidance"},
        "excerpt": "Tutors should provide early guidance.",
    }
    assert "Verified student fact" in result.data["recommendations"][0]["explanation"]
    assert result.data["policy_context_used"] is True


def test_rag_failure_preserves_qualified_fact_based_action_as_partial():
    policy = policy_gateway(
        PolicyContextResult(query="query", error_code="RAG_RETRIEVAL_UNAVAILABLE")
    )
    result = run(
        make_agent(policy),
        state_with(risk_result([factor("progress", "MEDIUM")])),
    )

    recommendation = result.data["recommendations"][0]
    assert result.status == "PARTIAL"
    assert recommendation["policy_evidence"] == []
    assert recommendation["policy_context_used"] is False
    assert "not a statement of university policy" in recommendation["explanation"]
    assert result.data["policy_context_used"] is False


def test_rag_exception_is_controlled_and_does_not_expose_details():
    policy = policy_gateway()
    policy.retrieve_policy.side_effect = RuntimeError(
        "qdrant://internal-host credential=secret"
    )
    result = run(
        make_agent(policy),
        state_with(risk_result([factor("progress", "MEDIUM")])),
    )

    assert result.status == "PARTIAL"
    assert result.data["recommendations"]
    assert "internal-host" not in repr(result)
    assert "credential" not in repr(result)


def test_candidate_without_source_or_metadata_is_not_policy_evidence():
    no_source = PolicyEvidenceCandidate("id", "text", 0.5, None, {})
    policy = policy_gateway(PolicyContextResult("query", (no_source,)))
    result = run(make_agent(policy), state_with(risk_result([factor("progress")])))

    assert result.status == "PARTIAL"
    assert result.data["recommendations"][0]["policy_evidence"] == []


def test_explicit_policy_conflict_omits_factor_recommendations():
    conflict = candidate(policy_status="CONFLICT")
    policy = policy_gateway(PolicyContextResult("query", (conflict,)))
    result = run(make_agent(policy), state_with(risk_result([factor("progress")])))

    assert result.status == "PARTIAL"
    assert result.data["recommendations"] == []
    assert "Conflicting policy evidence" in result.data["missing_information"][0]


def test_unknown_factor_is_partial_and_does_not_retrieve_or_invent_action():
    policy = policy_gateway()
    result = run(make_agent(policy), state_with(risk_result([factor("other")])))

    assert result.status == "PARTIAL"
    assert result.data["recommendations"] == []
    policy.retrieve_policy.assert_not_awaited()


def test_missing_failed_or_misordered_risk_is_partial():
    missing = run(make_agent(policy_gateway()), state_with(None, completed=[]))
    failed = run(
        make_agent(policy_gateway()),
        state_with(risk_result(status="FAILED"), completed=["risk"]),
    )
    misordered = run(
        make_agent(policy_gateway()),
        state_with(
            risk_result([factor("progress")]),
            selected=["recommendation", "risk"],
            completed=["risk"],
        ),
    )
    prerequisite_order = run(
        make_agent(policy_gateway()),
        state_with(
            risk_result([factor("progress")]),
            selected=["study_rights", "progress", "risk", "recommendation"],
            completed=["study_rights", "progress", "risk"],
        ),
    )

    for result in (missing, failed, misordered, prerequisite_order):
        assert result.status == "PARTIAL"
        assert result.data["recommendations"] == []


def test_partial_risk_preserves_confirmed_recommendations_but_stays_partial():
    result = run(
        make_agent(policy_gateway()),
        state_with(risk_result([factor("progress")], complete=False, status="PARTIAL")),
    )

    assert result.status == "PARTIAL"
    assert result.data["recommendations"]


def test_complete_no_risk_returns_no_recommendations_without_rag_call():
    policy = policy_gateway()
    result = run(
        make_agent(policy),
        state_with(risk_result([], complete=True, level="NONE")),
    )

    assert result.status == "SUCCESS"
    assert result.data["assessment_status"] == "COMPLETE"
    assert result.data["recommendations"] == []
    assert "no confirmed tutor intervention" in result.summary.lower()
    policy.retrieve_policy.assert_not_awaited()


def test_registry_contains_real_recommendation_agent():
    assert create_default_agent_registry().get("recommendation") is RecommendationAgent
