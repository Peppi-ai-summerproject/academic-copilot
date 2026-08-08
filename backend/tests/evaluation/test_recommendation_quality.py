"""Objective recommendation-quality evaluation for Issue #116."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.recommendation_agent import RecommendationAgent
from app.agents.state import create_initial_state
from app.agents.types import AgentResult
from app.gateways.policy_context import (
    PolicyContextResult,
    PolicyEvidenceCandidate,
)
from app.services.progress_explanation_service import (
    ProgressExplanationInput,
    ProgressExplanationService,
)
from app.services.risk_explanation_service import (
    RiskExplanationInput,
    RiskExplanationService,
)
from tests.evaluation.recommendation_scenarios import (
    SCENARIOS,
    SCENARIOS_BY_ID,
    RecommendationScenario,
    progress_factor,
)


class EvaluationPolicyGateway:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.queries: list[str] = []

    async def retrieve_policy(self, query: str, *, top_k: int = 3):
        self.queries.append(query)
        if not self.available:
            return PolicyContextResult(
                query=query,
                error_code="POLICY_CONTEXT_UNAVAILABLE",
            )
        return PolicyContextResult(
            query=query,
            candidates=(
                PolicyEvidenceCandidate(
                    chunk_id="policy-tutor-support",
                    text="Tutors should review verified concerns and agree on next steps.",
                    score=0.91,
                    source="Academic Policy",
                    metadata={"section": "Tutor support"},
                ),
            ),
        )


def evaluate(scenario: RecommendationScenario, *, student_id: int = 42) -> AgentResult:
    state = create_initial_state(
        user_message="Evaluate tutor recommendation",
        student_id=student_id,
    )
    state.selected_agents = ["risk", "recommendation"]
    state.completed_agents = ["risk"]
    state.agent_results["risk"] = AgentResult(
        agent_name="RiskDetectionAgent",
        route="risk",
        status="SUCCESS" if scenario.assessment_complete else "PARTIAL",
        summary="Deterministic evaluation risk result.",
        data={
            "student_id": student_id,
            "risk_level": scenario.risk_level,
            "risk_factors": list(scenario.risk_factors),
            "assessment_complete": scenario.assessment_complete,
            "unavailable_dimensions": list(scenario.unavailable_dimensions),
        },
    )
    for route in ("progress", "study_rights"):
        state.agent_results[route] = AgentResult(
            agent_name=f"{route.title()}Agent",
            route=route,
            status="SUCCESS",
            summary=f"Verified {route} evidence.",
            data={"source": route},
        )
    policy = EvaluationPolicyGateway(scenario.policy_mode == "available")
    agent = RecommendationAgent(gateway=object(), policy_gateway=policy)
    return asyncio.run(agent.run(state))


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.scenario_id)
def test_scenarios_preserve_expected_decisions_and_interventions(scenario) -> None:
    result = evaluate(scenario)
    assert tuple(
        item["recommendation_type"] for item in result.data["recommendations"]
    ) == scenario.expected_types
    assert tuple(
        item["intervention_type"] for item in result.data["interventions"]
    ) == scenario.expected_interventions


def test_healthy_student_is_not_escalated() -> None:
    result = evaluate(SCENARIOS_BY_ID["healthy_on_track"])
    assert result.data["recommendations"][0]["priority"] == "LOW"
    assert "no immediate tutor intervention" in result.data["recommendations"][0]["action"]
    assert all(
        item["intervention_type"] != "SCHEDULE_TUTOR_MEETING"
        for item in result.data["interventions"]
    )


def test_significant_delay_has_actionable_attention_and_matching_evidence() -> None:
    result = evaluate(SCENARIOS_BY_ID["significant_delay"])
    assert {item["action"] for item in result.data["recommendations"]} == {
        "Review the student's study plan.",
        "Schedule a tutor meeting.",
    }
    assert all(item["priority"] == "HIGH" for item in result.data["recommendations"])
    evidence = result.data["recommendations"][0]["student_evidence"][0]
    assert evidence["values"] == {
        "completed_ects": 60,
        "expected_ects": 120,
        "ects_deficit": 60,
    }


def test_study_right_concern_gets_distinct_specific_action() -> None:
    result = evaluate(SCENARIOS_BY_ID["study_right_concern"])
    assert result.data["recommendations"][0]["recommendation_type"] == "study_right"
    assert "study-right" in result.data["recommendations"][0]["action"].lower()
    assert all(
        item["recommendation_type"] != "progress"
        for item in result.data["recommendations"]
    )


def test_multiple_factors_have_no_duplicate_intervention_types() -> None:
    result = evaluate(SCENARIOS_BY_ID["multiple_risk_factors"])
    types = [item["intervention_type"] for item in result.data["interventions"]]
    assert len(types) == len(set(types))


def test_partial_data_is_tutor_visible_and_not_treated_as_zero() -> None:
    result = evaluate(SCENARIOS_BY_ID["partial_data"])
    rendered = result.data["rendered_recommendation"]["text"]
    assert result.status == "PARTIAL"
    assert result.data["data_status"] == "PARTIAL"
    assert result.data["unavailable_dimensions"] == ["tutor_meetings"]
    assert "Status: PARTIAL" in rendered
    assert "Unavailable: tutor_meetings" in rendered
    assert "zero meetings" not in rendered.lower()


def test_policy_grounding_and_unavailability_are_honest() -> None:
    supported = evaluate(SCENARIOS_BY_ID["policy_supported"])
    unavailable = evaluate(SCENARIOS_BY_ID["policy_unavailable"])
    supported_item = supported.data["recommendations"][0]
    unavailable_item = unavailable.data["recommendations"][0]
    assert supported_item["policy_evidence"][0]["source"] == "Academic Policy"
    assert supported_item["policy_context_used"] is True
    assert unavailable_item["policy_evidence"] == []
    assert unavailable_item["policy_context_used"] is False
    assert "not a statement of university policy" in unavailable_item["explanation"]


def test_repeated_and_equivalent_inputs_are_consistent() -> None:
    scenario = SCENARIOS_BY_ID["moderate_delay"]
    first = evaluate(scenario, student_id=42)
    repeated = evaluate(scenario, student_id=42)
    equivalent_student = evaluate(scenario, student_id=84)
    for result in (repeated, equivalent_student):
        assert result.data["recommendations"] == first.data["recommendations"]
        assert result.data["interventions"] == first.data["interventions"]
        assert result.data["rendered_recommendation"] == first.data["rendered_recommendation"]


def test_real_boundary_changes_only_at_the_approved_30_ects_rule() -> None:
    below = evaluate(SCENARIOS_BY_ID["boundary_29_ects"])
    boundary = evaluate(SCENARIOS_BY_ID["moderate_delay"])
    assert [item["priority"] for item in below.data["recommendations"]] == ["LOW"]
    assert [item["priority"] for item in boundary.data["recommendations"]] == [
        "MEDIUM",
        "MEDIUM",
    ]
    assert "SCHEDULE_TUTOR_MEETING" not in {
        item["intervention_type"] for item in below.data["interventions"]
    }
    assert "SCHEDULE_TUTOR_MEETING" in {
        item["intervention_type"] for item in boundary.data["interventions"]
    }


def test_explanations_preserve_canonical_risk_and_progress_values() -> None:
    risk_result = {
        "success": True,
        "student_id": 42,
        "assessment_status": "COMPLETE",
        "score": 50,
        "risk_level": "HIGH",
        "score_basis": "all_indicators",
        "policy_version": "academic-risk-v1",
        "indicator_contributions": [
            {
                "indicator_code": "academic_delay",
                "assigned_points": 50,
                "maximum_points": 50,
                "matched_rule_code": "DELAY_60_OR_MORE",
                "authoritative_source": "Issue #93 DelayDetectionService",
                "normalized_input": {"delay_ects": 60, "is_delayed": True},
                "explanation": "Verified academic delay contributes 50 points.",
            }
        ],
        "unavailable_indicators": [],
        "applied_overrides": [],
        "explanation": ["Verified academic delay contributes 50 points."],
    }
    progress_result = {
        "success": True,
        "progress": {
            "current_semester": 4,
            "completed_ects": 60,
            "expected_ects": 120,
            "difference_ects": -60,
            "remaining_to_expected_ects": 60,
            "progress_percentage": 50.0,
            "status": "BEHIND",
        },
    }
    risk = RiskExplanationService().explain(RiskExplanationInput(42, risk_result))
    progress = ProgressExplanationService().explain(
        ProgressExplanationInput(42, progress_result)
    )
    assert (risk.risk_score, risk.risk_level) == (50, "HIGH")
    assert risk.factors[0].evidence["delay_ects"] == 60
    assert (progress.completed_ects, progress.expected_ects) == (60, 120)
    assert progress.difference_ects == -60


def test_outputs_contain_no_unsupported_student_or_policy_claims() -> None:
    result = evaluate(SCENARIOS_BY_ID["policy_unavailable"])
    rendered = result.data["rendered_recommendation"]["text"]
    forbidden = ("course name", "meeting occurred", "university requires", "0 meetings")
    assert not any(claim in rendered.lower() for claim in forbidden)


def test_minimal_delay_documents_current_non_meeting_response() -> None:
    """A one-ECTS deficit still triggers a study-plan review, but no meeting."""
    result = evaluate(SCENARIOS_BY_ID["minimal_delay_no_escalation"])
    assert [item["intervention_type"] for item in result.data["interventions"]] == [
        "REVIEW_STUDY_PLAN"
    ]
    assert result.data["recommendations"][0]["student_evidence"][0]["values"][
        "ects_deficit"
    ] == 1
