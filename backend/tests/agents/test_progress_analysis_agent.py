"""Unit tests for the gateway-backed ProgressAnalysisAgent — Issue #166."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

from app.agents.progress_analysis_agent import (
    ProgressAnalysisAgent,
    _build_summary,
    _map_progress_status,
)


def _state(student_id: int | None = 1) -> Mock:
    return Mock(student_id=student_id)


def _student(success: bool = True) -> dict:
    if not success:
        return {"success": False, "error": "STUDENT_NOT_FOUND"}
    return {
        "success": True,
        "student": {"id": 1, "name": "Mikael Virtanen", "programme": "Business IT"},
    }


def _progress(status: str = "ON_TRACK", completed: int = 120, expected: int = 120) -> dict:
    return {
        "success": True,
        "progress": {
            "current_semester": 4,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": completed - expected,
            "remaining_to_expected_ects": max(expected - completed, 0),
            "progress_percentage": completed / expected * 100,
            "status": status,
        },
    }


def _gateway(student_result: dict | None = None, progress_result: dict | None = None) -> Mock:
    gateway = Mock()
    gateway.get_student = AsyncMock(return_value=student_result or _student())
    gateway.get_progress = AsyncMock(return_value=progress_result or _progress())
    return gateway


def run(agent: ProgressAnalysisAgent, student_id: int | None = 1):
    return asyncio.run(agent.run(_state(student_id)))


def test_agent_metadata() -> None:
    agent = ProgressAnalysisAgent(_gateway())
    assert agent.name == "ProgressAnalysisAgent"
    assert "progress" in agent.description.lower()


def test_missing_student_id_does_not_call_gateway() -> None:
    gateway = _gateway()
    result = run(ProgressAnalysisAgent(gateway), None)
    assert result.status == "FAILED"
    gateway.get_student.assert_not_awaited()
    gateway.get_progress.assert_not_awaited()


def test_student_not_found_stops_before_progress_lookup() -> None:
    gateway = _gateway(student_result=_student(False))
    result = run(ProgressAnalysisAgent(gateway), 999)
    assert result.status == "FAILED"
    assert "STUDENT_NOT_FOUND" in result.errors
    gateway.get_student.assert_awaited_once_with(999)
    gateway.get_progress.assert_not_awaited()


def test_progress_unavailable_returns_partial() -> None:
    gateway = _gateway(progress_result={"success": False, "error": "CURRICULUM_NOT_FOUND"})
    result = run(ProgressAnalysisAgent(gateway))
    assert result.status == "PARTIAL"
    assert "CURRICULUM_NOT_FOUND" in result.warnings
    explanation = result.data["progress_explanation"]
    assert explanation["data_status"] == "PARTIAL"
    assert explanation["completed_ects"] is None
    assert explanation["expected_ects"] is None
    assert "Assessment: PARTIAL" in result.summary
    assert "Availability" in result.summary
    assert "could not be verified" in result.summary


def test_on_track_result_preserves_contract() -> None:
    gateway = _gateway()
    result = run(ProgressAnalysisAgent(gateway))
    assert result.status == "SUCCESS"
    assert result.route == "progress"
    assert result.data["is_on_track"] is True
    assert result.data["completed_ects"] == 120
    explanation = result.data["progress_explanation"]
    assert explanation["data_status"] == "COMPLETE"
    assert explanation["completed_ects"] == result.data["completed_ects"]
    assert explanation["status"] == result.data["progress_status"]
    gateway.get_student.assert_awaited_once_with(1)
    gateway.get_progress.assert_awaited_once_with(1)


def test_behind_and_ahead_statuses() -> None:
    behind = run(ProgressAnalysisAgent(_gateway(progress_result=_progress("BEHIND", 60, 120))))
    ahead = run(ProgressAnalysisAgent(_gateway(progress_result=_progress("AHEAD", 150, 120))))
    assert behind.status == "PARTIAL" and behind.data["is_behind"] is True
    assert ahead.status == "SUCCESS" and ahead.data["is_ahead"] is True


def test_gateway_exception_returns_failed_result() -> None:
    gateway = _gateway()
    gateway.get_student.side_effect = RuntimeError("tool failure")
    result = run(ProgressAnalysisAgent(gateway))
    assert result.status == "FAILED"
    assert "tool failure" in result.errors[0]


def test_summary_and_status_helpers() -> None:
    behind = _build_summary("Anna", "BIT", 60, 120, -60, "BEHIND", 4, 50)
    on_track = _build_summary("Anna", "BIT", 120, 120, 0, "ON_TRACK", 4, 100)
    ahead = _build_summary("Anna", "BIT", 150, 120, 30, "AHEAD", 4, 125)
    assert "Status: BEHIND" in behind and "Difference: 60 ECTS behind" in behind
    assert "Assessment: PARTIAL" in behind
    assert "Status: ON_TRACK" in on_track and "Difference: 0 ECTS" in on_track
    assert "Status: AHEAD" in ahead and "Difference: 30 ECTS ahead" in ahead
    assert _map_progress_status("BEHIND") == "PARTIAL"
    assert _map_progress_status("ON_TRACK") == "SUCCESS"


def test_matias_progress_values_are_presented_without_recalculation() -> None:
    summary = _build_summary(
        "Matias Multiple", "Business IT", 5, 30, -25, "BEHIND", 1, 16.7
    )

    assert summary.startswith("Academic progress\nMatias Multiple · Business IT")
    assert "Status: BEHIND" in summary
    assert "Completed: 5 ECTS" in summary
    assert "Expected: 30 ECTS by semester 1" in summary
    assert "Difference: 25 ECTS behind" in summary
    assert "Progress: 16.7% of expected" in summary
