from __future__ import annotations

import asyncio

from app.agents.communication_agent import CommunicationAgent
from app.agents.state import create_initial_state
from app.agents.types import AgentResult


def result(route: str, summary: str, status: str = "SUCCESS", **data) -> AgentResult:
    return AgentResult(
        agent_name=f"{route.title()}Agent",
        route=route,
        status=status,
        summary=summary,
        data=data,
    )


def run_agent(*results: AgentResult, **state_changes):
    state = create_initial_state(user_message="Prepare a tutor response")
    for key, value in state_changes.items():
        setattr(state, key, value)
    state.agent_results = {item.route: item for item in results}
    return asyncio.run(CommunicationAgent().run(state))


def test_formats_complete_recommendation_as_advisory_tutor_message():
    recommendation = result(
        "recommendation",
        "Two supported actions.",
        recommendations=[
            {"priority": "HIGH", "action": "Schedule a tutor meeting."},
            {"priority": "MEDIUM", "action": "Review the study plan."},
        ],
    )

    output = run_agent(recommendation)

    assert output.status == "SUCCESS"
    assert "Recommended actions (advisory)" in output.data["formatted_message"]
    assert "HIGH priority: Schedule a tutor meeting. (advisory)" in output.data["formatted_message"]
    assert output.data["delivery_status"] == "NOT_SENT"


def test_uses_recommendation_template_presentation_when_available():
    recommendation = result(
        "recommendation",
        "One supported action.",
        recommendations=[{"priority": "HIGH", "action": "Legacy action."}],
        rendered_recommendation={
            "text": "Recommendation\n\nRecommended actions (advisory)\n"
            "1. HIGH priority: Template action. (advisory)",
            "sections": ["recommendation", "interventions"],
            "scenarios": ["progress"],
            "data_status": "COMPLETE",
        },
    )

    output = run_agent(recommendation)

    assert "Template action" in output.data["formatted_message"]
    assert "Legacy action" not in output.data["formatted_message"]
    assert "recommendation_presentation" in output.data["sections_included"]


def test_includes_verified_facts_without_recalculating_them():
    output = run_agent(
        result("progress", "Verified progress: 90 of 120 ECTS."),
        result("study_rights", "Verified study right: active."),
        result("risk", "Verified risk: MEDIUM."),
    )

    message = output.data["formatted_message"]
    assert "Verified facts" in message
    assert "Verified progress: 90 of 120 ECTS." in message
    assert "Verified study right: active." in message
    assert "Verified risk: MEDIUM." in message


def test_verified_facts_are_separate_from_recommended_actions():
    output = run_agent(
        result("risk", "A progress risk is confirmed."),
        result(
            "recommendation",
            "One action.",
            recommendations=[{"priority": "HIGH", "action": "Review the study plan."}],
        ),
    )

    message = output.data["formatted_message"]
    assert message.index("Verified facts") < message.index("Recommended actions (advisory)")


def test_available_conversation_context_is_recorded_but_identifiers_are_not_exposed():
    output = run_agent(
        result("progress", "Progress is verified."),
        conversation_id="conversation-1",
        telegram_user_id=101,
        telegram_chat_id=202,
    )

    assert output.data["context_used"] is True
    assert output.data["conversation_id"] == "conversation-1"
    assert "101" not in output.data["formatted_message"]
    assert "202" not in output.data["formatted_message"]


def test_missing_conversation_context_still_formats_current_results():
    output = run_agent(result("progress", "Current progress is verified."))

    assert output.data["context_used"] is False
    assert "Current progress is verified." in output.data["formatted_message"]


def test_partial_results_preserve_facts_and_warn_against_no_risk_conclusion():
    output = run_agent(
        result("progress", "Confirmed progress information.", "PARTIAL"),
        selected_agents=["progress", "risk", "communication"],
    )

    assert output.status == "PARTIAL"
    assert "Confirmed progress information." in output.data["formatted_message"]
    assert "Do not treat missing information as confirmation that there is no risk" in output.data["formatted_message"]
    assert "no risk" not in output.data["formatted_message"].lower().split("availability note")[0]


def test_failed_results_do_not_expose_internal_errors_or_fabricate_an_answer():
    failed = AgentResult(
        agent_name="RiskDetectionAgent",
        route="risk",
        status="FAILED",
        summary="Risk service failed.",
        errors=["postgresql://secret@internal-db:5432"],
    )

    output = run_agent(failed)

    message = output.data["formatted_message"]
    assert output.status == "PARTIAL"
    assert "Sufficient verified information is unavailable" in message
    assert "postgresql" not in message.lower()
    assert "internal-db" not in message
    assert "Risk service failed" not in message


def test_payload_is_plain_text_for_existing_telegram_delivery_boundary():
    output = run_agent(result("progress", "Progress is on track."))

    assert output.data["channel"] == "telegram"
    assert isinstance(output.data["formatted_message"], str)
    assert "parse_mode" not in output.data
    assert output.data["delivery_status"] == "NOT_SENT"


def test_source_agents_include_only_usable_results_in_stable_order():
    output = run_agent(
        result("risk", "Risk verified."),
        result("progress", "Progress verified."),
    )

    assert output.data["source_agents"] == ["progress", "risk"]


def test_agent_has_no_gateway_or_telegram_client_dependency():
    agent = CommunicationAgent()

    assert vars(agent) == {}


def test_formats_structured_reporting_result_for_tutor_delivery():
    report = result(
        "reporting",
        "Partial report: verified risk requires review.",
        performance={"status": "available", "summary": "90 of 120 ECTS completed."},
        study_right={"status": "available", "summary": "Study right is active."},
        risks={"status": "available", "summary": "HIGH risk is verified."},
        upcoming_actions={
            "status": "available",
            "items": [{"priority": "HIGH", "action": "Review the study plan.", "advisory": True}],
        },
    )

    output = run_agent(report, selected_agents=["reporting", "communication"])

    message = output.data["formatted_message"]
    assert "90 of 120 ECTS completed." in message
    assert "Study right is active." in message
    assert "HIGH risk is verified." in message
    assert "HIGH priority: Review the study plan. (advisory)" in message
