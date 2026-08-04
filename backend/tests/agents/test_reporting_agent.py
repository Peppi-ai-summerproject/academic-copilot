from __future__ import annotations

import asyncio
import json
from datetime import date

from app.agents.reporting_agent import ReportingAgent
from app.agents.state import create_initial_state
from app.agents.types import AgentResult


def result(route: str, summary: str, status: str = "SUCCESS", **data) -> AgentResult:
    return AgentResult(
        agent_name=f"{route.title()}Agent",
        route=route,
        status=status,
        summary=summary,
        data=data,
        evidence=[f"Verified evidence from {route}."],
    )


def complete_results() -> list[AgentResult]:
    return [
        result(
            "progress", "Ada has completed 90 of 120 expected ECTS.",
            student_name="Ada", programme="Computing", current_semester=4,
            completed_ects=90, expected_ects=120, difference_ects=-30,
            progress_percentage=75.0, progress_status="BEHIND",
            internal_request_id="do-not-export",
        ),
        result(
            "study_rights", "Ada's study right is active.",
            study_right_status="ACTIVE", extension_count=0,
            is_expiring_soon=False, expiration_date="2028-07-31",
            needs_attention=False, urgency="LOW",
        ),
        result(
            "risk", "Ada has HIGH academic risk.",
            risk_level="HIGH", assessment_complete=True,
            risk_factors=[{
                "dimension": "progress", "level": "HIGH",
                "reason": "30 ECTS behind.", "values": {"difference_ects": -30},
                "evidence_source": "progress",
            }],
        ),
        result(
            "recommendation", "One policy-grounded advisory action.",
            recommendations=[{
                "priority": "HIGH", "action": "Review the study plan.",
                "explanation": "Verified progress requires tutor review.",
                "source_agents": ["risk", "progress"],
                "policy_evidence": [{"chunk": "must not be exported"}],
            }],
        ),
    ]


def run_agent(*results: AgentResult, student_id: int = 42):
    state = create_initial_state(user_message="Create report", student_id=student_id)
    state.agent_results = {item.route: item for item in results}
    return asyncio.run(ReportingAgent().run(state))


def test_generates_complete_structured_tutor_report():
    output = run_agent(*complete_results())

    assert output.status == "SUCCESS"
    assert output.data["report_type"] == "student_tutor_summary"
    assert output.data["overall_status"] == "complete"
    assert output.data["student_id"] == 42
    assert output.data["schema_version"] == "1.0"


def test_uses_verified_summary_as_key_insight_without_recalculation():
    output = run_agent(*complete_results())

    assert output.data["executive_summary"] == "Ada has HIGH academic risk."
    assert output.data["performance"]["summary"] == "Ada has completed 90 of 120 expected ECTS."


def test_preserves_performance_study_right_and_risk_values_and_evidence():
    output = run_agent(*complete_results())

    assert output.data["performance"]["facts"]["completed_ects"] == 90
    assert output.data["study_right"]["facts"]["study_right_status"] == "ACTIVE"
    assert output.data["risks"]["risk_level"] == "HIGH"
    assert output.data["risks"]["items"][0]["reason"] == "30 ECTS behind."
    assert output.data["risks"]["evidence"] == ["Verified evidence from risk."]


def test_preserves_recommendation_priority_and_advisory_boundary():
    output = run_agent(*complete_results())

    action = output.data["upcoming_actions"]["items"][0]
    assert action["priority"] == "HIGH"
    assert action["action"] == "Review the study plan."
    assert action["advisory"] is True
    assert "policy_evidence" not in action


def test_includes_calendar_events_only_when_verified_result_is_supplied():
    calendar = result(
        "calendar", "One verified event.",
        events=[{"name": "Registration deadline", "date": date(2026, 9, 1)}],
    )

    output = run_agent(*complete_results(), calendar)

    assert output.data["upcoming_events"] == {
        "status": "available",
        "items": [{"name": "Registration deadline", "date": "2026-09-01"}],
        "source_agent": "calendar",
    }


def test_absent_calendar_data_is_explicitly_unavailable():
    output = run_agent(*complete_results())

    assert output.data["upcoming_events"]["status"] == "unavailable"
    assert output.data["upcoming_events"]["items"] == []


def test_export_payload_is_json_serializable_and_does_not_generate_a_file():
    output = run_agent(*complete_results())

    encoded = json.dumps(output.data)
    assert "student_tutor_summary" in encoded
    assert output.data["export"] == {
        "format": "structured_data", "schema_version": "1.0", "file_generated": False,
    }


def test_partial_results_retain_facts_without_claiming_no_risk():
    output = run_agent(complete_results()[0])

    assert output.status == "PARTIAL"
    assert output.data["overall_status"] == "partial"
    assert output.data["performance"]["status"] == "available"
    assert output.data["risks"]["status"] == "unavailable"
    assert "no risk" not in output.data["executive_summary"].lower()


def test_failed_results_do_not_expose_errors_or_fabricate_report_sections():
    failed = AgentResult(
        agent_name="RiskDetectionAgent", route="risk", status="FAILED",
        summary="Database internal-db failed.", errors=["password=secret"],
    )

    output = run_agent(failed)
    encoded = json.dumps(output.data)

    assert output.status == "PARTIAL"
    assert output.data["overall_status"] == "unavailable"
    assert "Sufficient verified information is unavailable" in output.summary
    assert "internal-db" not in encoded
    assert "secret" not in encoded


def test_records_provenance_and_filters_internal_metadata():
    output = run_agent(*complete_results())
    encoded = json.dumps(output.data)

    assert output.data["source_agents"] == [
        "progress", "study_rights", "risk", "recommendation",
    ]
    assert output.data["performance"]["source_agent"] == "progress"
    assert "internal_request_id" not in encoded
    assert "must not be exported" not in encoded


def test_agent_has_no_gateway_repository_exporter_or_network_dependency():
    agent = ReportingAgent()

    assert vars(agent) == {}
