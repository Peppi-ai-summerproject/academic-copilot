"""Unit tests for ProgressAnalysisAgent — Issue #81."""

from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.agents.progress_analysis_agent import (
    ProgressAnalysisAgent,
    _build_summary,
    _map_progress_status,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_state(student_id=1):
    state = Mock()
    state.student_id = student_id
    return state


def _make_student_result(student_id=1, name="Mikael Virtanen", programme="Business IT"):
    return {
        "success": True,
        "student": {
            "id": student_id,
            "student_number": "S001",
            "name": name,
            "programme": programme,
            "status": "ACTIVE",
        },
    }


def _make_progress_result(
    completed=120, expected=120, status="ON_TRACK", semester=4, diff=0
):
    return {
        "success": True,
        "progress": {
            "student_id": 1,
            "student_number": "S001",
            "student_name": "Mikael Virtanen",
            "programme": "Business IT",
            "current_semester": semester,
            "completed_ects": completed,
            "expected_ects": expected,
            "difference_ects": diff,
            "remaining_to_expected_ects": max(expected - completed, 0),
            "progress_percentage": round((completed / expected * 100), 2) if expected else 0.0,
            "status": status,
        },
    }


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Agent metadata ────────────────────────────────────────────────────────────

def test_agent_has_name():
    agent = ProgressAnalysisAgent()
    assert agent.name == "ProgressAnalysisAgent"


def test_agent_has_description():
    agent = ProgressAnalysisAgent()
    assert agent.description
    assert "progress" in agent.description.lower()


# ── Missing student_id ────────────────────────────────────────────────────────

def test_run_returns_failed_when_student_id_is_none():
    agent = ProgressAnalysisAgent()
    state = _make_state(student_id=None)
    result = run(agent.run(state))
    assert result.status == "FAILED"
    assert result.route == "progress"
    assert len(result.errors) > 0


# ── Student not found ─────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
def test_run_returns_failed_when_student_not_found(
    mock_progress_svc, mock_student_svc, mock_session
):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = {"success": False, "error": "STUDENT_NOT_FOUND"}
    mock_student_svc.return_value = student_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state(student_id=999)))

    assert result.status == "FAILED"
    assert result.route == "progress"
    assert "STUDENT_NOT_FOUND" in result.errors


# ── Progress unavailable ──────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_run_returns_partial_when_progress_unavailable(
    mock_pr, mock_sr, mock_ps, mock_ss, mock_session
):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc

    progress_svc = Mock()
    progress_svc.get_progress.return_value = {
        "success": False, "error": "CURRICULUM_NOT_FOUND"
    }
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    assert result.status == "PARTIAL"
    assert result.route == "progress"
    assert len(result.warnings) > 0


# ── Successful on-track progress ──────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_run_returns_success_for_on_track_student(
    mock_pr, mock_sr, mock_ps, mock_ss, mock_session
):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc

    progress_svc = Mock()
    progress_svc.get_progress.return_value = _make_progress_result(
        completed=120, expected=120, status="ON_TRACK", diff=0
    )
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    assert result.status == "SUCCESS"
    assert result.route == "progress"
    assert result.data["is_on_track"] is True
    assert result.data["is_behind"] is False
    assert result.data["completed_ects"] == 120


# ── Behind student ────────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_run_returns_partial_for_behind_student(
    mock_pr, mock_sr, mock_ps, mock_ss, mock_session
):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc

    progress_svc = Mock()
    progress_svc.get_progress.return_value = _make_progress_result(
        completed=60, expected=120, status="BEHIND", diff=-60
    )
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    assert result.status == "PARTIAL"
    assert result.data["is_behind"] is True
    assert result.data["completed_ects"] == 60
    assert result.data["expected_ects"] == 120
    assert "behind" in result.summary.lower()


# ── Ahead student ─────────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_run_returns_success_for_ahead_student(
    mock_pr, mock_sr, mock_ps, mock_ss, mock_session
):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc

    progress_svc = Mock()
    progress_svc.get_progress.return_value = _make_progress_result(
        completed=150, expected=120, status="AHEAD", diff=30
    )
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    assert result.status == "SUCCESS"
    assert result.data["is_ahead"] is True
    assert "ahead" in result.summary.lower()


# ── Database error ────────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
def test_run_returns_failed_on_database_exception(mock_sr, mock_ss, mock_session):
    db = Mock()
    mock_session.return_value = db
    mock_sr.side_effect = RuntimeError("DB crash")

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    assert result.status == "FAILED"
    assert result.route == "progress"
    assert len(result.errors) > 0


# ── Session management ────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_session_closes_on_success(mock_pr, mock_sr, mock_ps, mock_ss, mock_session):
    db = Mock()
    mock_session.return_value = db
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc
    progress_svc = Mock()
    progress_svc.get_progress.return_value = _make_progress_result()
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    run(agent.run(_make_state()))
    db.close.assert_called_once()


# ── Result structure ──────────────────────────────────────────────────────────

@patch("app.agents.progress_analysis_agent.SessionLocal")
@patch("app.agents.progress_analysis_agent.StudentService")
@patch("app.agents.progress_analysis_agent.ProgressService")
@patch("app.agents.progress_analysis_agent.StudentRepository")
@patch("app.agents.progress_analysis_agent.ProgressRepository")
def test_result_data_has_expected_fields(mock_pr, mock_sr, mock_ps, mock_ss, mock_session):
    mock_session.return_value = Mock()
    student_svc = Mock()
    student_svc.get_student.return_value = _make_student_result()
    mock_ss.return_value = student_svc
    progress_svc = Mock()
    progress_svc.get_progress.return_value = _make_progress_result()
    mock_ps.return_value = progress_svc

    agent = ProgressAnalysisAgent()
    result = run(agent.run(_make_state()))

    for field in ["student_id", "student_name", "programme", "completed_ects",
                  "expected_ects", "progress_status", "is_behind", "is_ahead", "is_on_track"]:
        assert field in result.data, f"Missing field: {field}"


# ── Helper function tests ─────────────────────────────────────────────────────

def test_build_summary_behind():
    summary = _build_summary("Anna", "BIT", 60, 120, -60, "BEHIND", 4, 50.0)
    assert "behind" in summary.lower()
    assert "Anna" in summary
    assert "60" in summary

def test_build_summary_on_track():
    summary = _build_summary("Anna", "BIT", 120, 120, 0, "ON_TRACK", 4, 100.0)
    assert "on track" in summary.lower()

def test_build_summary_ahead():
    summary = _build_summary("Anna", "BIT", 150, 120, 30, "AHEAD", 4, 125.0)
    assert "ahead" in summary.lower()

def test_map_progress_status_behind_returns_partial():
    assert _map_progress_status("BEHIND") == "PARTIAL"

def test_map_progress_status_on_track_returns_success():
    assert _map_progress_status("ON_TRACK") == "SUCCESS"

def test_map_progress_status_ahead_returns_success():
    assert _map_progress_status("AHEAD") == "SUCCESS"
