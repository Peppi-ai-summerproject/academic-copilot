"""Unit tests for the Academic Tool Gateway — Issue #165."""

from __future__ import annotations

import asyncio
from unittest.mock import Mock

import pytest

from app.gateways.academic_tools import (
    AcademicToolGateway,
    AcademicToolGatewayError,
    MCPAcademicToolGateway,
)


def test_gateway_delegates_student_lookup() -> None:
    response = {"success": True, "student": {"id": 42}}
    student_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(student_tool=student_tool)

    result = asyncio.run(gateway.get_student(42))

    assert result is response
    student_tool.assert_called_once_with(42)


def test_gateway_delegates_progress_lookup() -> None:
    response = {"success": True, "progress": {"completed_ects": 120}}
    progress_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(progress_tool=progress_tool)

    result = asyncio.run(gateway.get_progress(7))

    assert result is response
    progress_tool.assert_called_once_with(7)


def test_gateway_delegates_study_right_lookup() -> None:
    response = {"success": False, "error": "STUDY_RIGHT_NOT_FOUND"}
    study_right_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(study_right_tool=study_right_tool)

    result = asyncio.run(gateway.get_study_right(9))

    assert result is response
    study_right_tool.assert_called_once_with(9)


def test_gateway_delegates_upcoming_events_lookup() -> None:
    response = {"success": True, "events": []}
    events_tool = Mock(return_value=response)
    gateway = MCPAcademicToolGateway(upcoming_events_tool=events_tool)

    result = asyncio.run(gateway.get_upcoming_events())

    assert result is response
    events_tool.assert_called_once_with()


def test_gateway_implements_protocol() -> None:
    assert isinstance(MCPAcademicToolGateway(), AcademicToolGateway)


def test_gateway_rejects_invalid_tool_response() -> None:
    gateway = MCPAcademicToolGateway(student_tool=Mock(return_value=None))

    with pytest.raises(AcademicToolGatewayError, match="get_student"):
        asyncio.run(gateway.get_student(1))
