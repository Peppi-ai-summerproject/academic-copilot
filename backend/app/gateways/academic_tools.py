"""Boundary between academic agents and the existing MCP tool ecosystem.

The gateway deliberately exposes only the operations required by the existing
Progress Analysis and Study Rights agents. Additional operations should be
added when an agent has a concrete need for them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from app.mcp.tools.progress import get_progress
from app.mcp.tools.student import get_student
from app.mcp.tools.study_right import get_study_right
from app.mcp.tools.events import get_upcoming_events

ToolResponse = dict[str, Any]
AcademicTool = Callable[[int], ToolResponse]
EventTool = Callable[[], ToolResponse]


class AcademicToolGatewayError(RuntimeError):
    """Raised when an MCP tool violates the gateway response contract."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")


@runtime_checkable
class AcademicToolGateway(Protocol):
    """Academic operations available to agents.

    Agents depend on this protocol rather than database sessions,
    repositories, services, or concrete MCP infrastructure.
    """

    async def get_student(self, student_id: int) -> ToolResponse: ...

    async def get_progress(self, student_id: int) -> ToolResponse: ...

    async def get_study_right(self, student_id: int) -> ToolResponse: ...

    async def get_upcoming_events(self) -> ToolResponse: ...


class MCPAcademicToolGateway:
    """In-process adapter over the existing synchronous MCP tool functions.

    Tool callables are injectable so agents and workflows can be tested without
    a database or running MCP transport. Synchronous calls run in a worker
    thread so they do not block the async LangGraph execution path.
    """

    def __init__(
        self,
        *,
        student_tool: AcademicTool = get_student,
        progress_tool: AcademicTool = get_progress,
        study_right_tool: AcademicTool = get_study_right,
        upcoming_events_tool: EventTool = get_upcoming_events,
    ) -> None:
        self._student_tool = student_tool
        self._progress_tool = progress_tool
        self._study_right_tool = study_right_tool
        self._upcoming_events_tool = upcoming_events_tool

    async def get_student(self, student_id: int) -> ToolResponse:
        return await self._invoke("get_student", self._student_tool, student_id)

    async def get_progress(self, student_id: int) -> ToolResponse:
        return await self._invoke("get_progress", self._progress_tool, student_id)

    async def get_study_right(self, student_id: int) -> ToolResponse:
        return await self._invoke(
            "get_study_right", self._study_right_tool, student_id
        )

    async def get_upcoming_events(self) -> ToolResponse:
        return await self._invoke_no_args(
            "get_upcoming_events", self._upcoming_events_tool
        )

    @staticmethod
    async def _invoke(
        tool_name: str,
        tool: AcademicTool,
        student_id: int,
    ) -> ToolResponse:
        response = await asyncio.to_thread(tool, student_id)
        if not isinstance(response, dict):
            raise AcademicToolGatewayError(
                tool_name,
                f"expected a dictionary response, got {type(response).__name__}",
            )
        return response

    @staticmethod
    async def _invoke_no_args(
        tool_name: str,
        tool: EventTool,
    ) -> ToolResponse:
        response = await asyncio.to_thread(tool)
        if not isinstance(response, dict):
            raise AcademicToolGatewayError(
                tool_name,
                f"expected a dictionary response, got {type(response).__name__}",
            )
        return response
