"""Unit tests for the gateway-backed StudyRightsAgent — Issue #166."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

from app.agents.study_rights_agent import StudyRightsAgent, _build_summary, _calculate_urgency


def _state(student_id: int | None = 1) -> Mock:
    return Mock(student_id=student_id)


def _student(success: bool = True) -> dict:
    if not success:
        return {"success": False, "error": "STUDENT_NOT_FOUND"}
    return {"success": True, "student": {"id": 1, "name": "Mikael Virtanen", "programme": "Business IT"}}


def _study_right(status: str = "ACTIVE", extension_count: int = 0) -> dict:
    return {
        "success": True,
        "study_right": {
            "status": status,
            "extension_count": extension_count,
            "expiration_date": date(2028, 5, 31),
            "is_expiring_soon": status == "EXPIRES_SOON",
        },
    }


def _gateway(student_result: dict | None = None, study_right_result: dict | None = None) -> Mock:
    gateway = Mock()
    gateway.get_student = AsyncMock(return_value=student_result or _student())
    gateway.get_study_right = AsyncMock(return_value=study_right_result or _study_right())
    return gateway


def run(agent: StudyRightsAgent, student_id: int | None = 1):
    return asyncio.run(agent.run(_state(student_id)))


def test_agent_metadata() -> None:
    agent = StudyRightsAgent(_gateway())
    assert agent.name == "StudyRightsAgent"
    assert "study right" in agent.description.lower()


def test_missing_student_id_does_not_call_gateway() -> None:
    gateway = _gateway()
    result = run(StudyRightsAgent(gateway), None)
    assert result.status == "FAILED"
    gateway.get_student.assert_not_awaited()
    gateway.get_study_right.assert_not_awaited()


def test_student_not_found_stops_before_study_right_lookup() -> None:
    gateway = _gateway(student_result=_student(False))
    result = run(StudyRightsAgent(gateway), 999)
    assert result.status == "FAILED"
    assert "STUDENT_NOT_FOUND" in result.errors
    gateway.get_student.assert_awaited_once_with(999)
    gateway.get_study_right.assert_not_awaited()


def test_study_right_unavailable_returns_partial() -> None:
    gateway = _gateway(study_right_result={"success": False, "error": "STUDY_RIGHT_NOT_FOUND"})
    result = run(StudyRightsAgent(gateway))
    assert result.status == "PARTIAL"
    assert "STUDY_RIGHT_NOT_FOUND" in result.warnings


def test_active_result_preserves_contract() -> None:
    gateway = _gateway()
    result = run(StudyRightsAgent(gateway))
    assert result.status == "SUCCESS"
    assert result.route == "study_rights"
    assert result.data["needs_attention"] is False
    gateway.get_student.assert_awaited_once_with(1)
    gateway.get_study_right.assert_awaited_once_with(1)


def test_risk_statuses_return_partial() -> None:
    expiring = run(StudyRightsAgent(_gateway(study_right_result=_study_right("EXPIRES_SOON"))))
    expired = run(StudyRightsAgent(_gateway(study_right_result=_study_right("EXPIRED"))))
    assert expiring.status == "PARTIAL" and expiring.data["urgency"] == "HIGH"
    assert expired.status == "PARTIAL" and expired.data["urgency"] == "CRITICAL"


def test_gateway_exception_returns_failed_result() -> None:
    gateway = _gateway()
    gateway.get_student.side_effect = RuntimeError("tool failure")
    result = run(StudyRightsAgent(gateway))
    assert result.status == "FAILED"
    assert "tool failure" in result.errors[0]


def test_summary_and_urgency_helpers() -> None:
    assert _calculate_urgency("EXPIRED", 0) == "CRITICAL"
    assert _calculate_urgency("EXPIRES_SOON", 2) == "CRITICAL"
    assert _calculate_urgency("EXTENDED", 1) == "MEDIUM"
    assert _calculate_urgency("ACTIVE", 0) == "LOW"
    assert "expired" in _build_summary("Anna", "BIT", "EXPIRED", 0, "2024-01-01", True).lower()
    assert "active" in _build_summary("Anna", "BIT", "ACTIVE", 0, "2028-01-01", False).lower()
