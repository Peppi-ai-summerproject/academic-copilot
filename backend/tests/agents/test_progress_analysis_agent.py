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


def test_on_track_result_preserves_contract() -> None:
    gateway = _gateway()
    result = run(ProgressAnalysisAgent(gateway))
    assert result.status == "SUCCESS"
    assert result.route == "progress"
    assert result.data["is_on_track"] is True
    assert result.data["completed_ects"] == 120
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
    assert "behind" in _build_summary("Anna", "BIT", 60, 120, -60, "BEHIND", 4, 50).lower()
    assert "on track" in _build_summary("Anna", "BIT", 120, 120, 0, "ON_TRACK", 4, 100).lower()
    assert "ahead" in _build_summary("Anna", "BIT", 150, 120, 30, "AHEAD", 4, 125).lower()
    assert _map_progress_status("BEHIND") == "PARTIAL"
    assert _map_progress_status("ON_TRACK") == "SUCCESS"
