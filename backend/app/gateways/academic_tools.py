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
from app.mcp.tools.search_students import search_students
from app.mcp.tools.courses import get_course, search_courses
from app.mcp.tools.teachers import get_teacher, search_teachers
from app.mcp.tools.enrollments import (
    get_course_roster,
    get_enrollment,
    get_student_enrollments,
)
from app.mcp.tools.results import get_course_results, get_student_results, get_course_completion_analytics

ToolResponse = dict[str, Any]
AcademicTool = Callable[[int], ToolResponse]
EventTool = Callable[[], ToolResponse]
SearchTool = Callable[..., ToolResponse]


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

    async def search_students(self, **kwargs: Any) -> ToolResponse: ...

    async def get_course(self, **kwargs: Any) -> ToolResponse: ...

    async def search_courses(self, **kwargs: Any) -> ToolResponse: ...

    async def get_teacher(self, teacher_id: int) -> ToolResponse: ...

    async def search_teachers(self, **kwargs: Any) -> ToolResponse: ...
    async def get_course_results(self, **kwargs: Any) -> ToolResponse: ...
    async def get_student_results(self, **kwargs: Any) -> ToolResponse: ...
    async def get_course_completion_analytics(self, **kwargs: Any) -> ToolResponse: ...

    async def get_course_roster(self, **kwargs: Any) -> ToolResponse: ...

    async def get_student_enrollments(self, **kwargs: Any) -> ToolResponse: ...

    async def get_enrollment(self, **kwargs: Any) -> ToolResponse: ...


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
        search_students_tool: SearchTool = search_students,
        course_tool: SearchTool = get_course,
        search_courses_tool: SearchTool = search_courses,
        teacher_tool: AcademicTool = get_teacher,
        search_teachers_tool: SearchTool = search_teachers,
        course_roster_tool: SearchTool = get_course_roster,
        student_enrollments_tool: SearchTool = get_student_enrollments,
        enrollment_tool: SearchTool = get_enrollment,
        course_results_tool: SearchTool = get_course_results,
        student_results_tool: SearchTool = get_student_results,
    ) -> None:
        self._student_tool = student_tool
        self._progress_tool = progress_tool
        self._study_right_tool = study_right_tool
        self._upcoming_events_tool = upcoming_events_tool
        self._search_students_tool = search_students_tool
        self._course_tool = course_tool
        self._search_courses_tool = search_courses_tool
        self._teacher_tool = teacher_tool
        self._search_teachers_tool = search_teachers_tool
        self._course_roster_tool = course_roster_tool
        self._student_enrollments_tool = student_enrollments_tool
        self._enrollment_tool = enrollment_tool
        self._course_results_tool = course_results_tool
        self._student_results_tool = student_results_tool

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

    async def search_students(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("search_students", self._search_students_tool, kwargs)

    async def get_course(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_course", self._course_tool, kwargs)

    async def search_courses(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("search_courses", self._search_courses_tool, kwargs)

    async def get_teacher(self, teacher_id: int) -> ToolResponse:
        return await self._invoke("get_teacher", self._teacher_tool, teacher_id)

    async def search_teachers(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("search_teachers", self._search_teachers_tool, kwargs)
    async def get_course_results(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_course_results", self._course_results_tool, kwargs)
    async def get_student_results(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_student_results", self._student_results_tool, kwargs)
    async def get_course_completion_analytics(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_course_completion_analytics", self._completion_analytics_tool, kwargs)

    async def get_course_roster(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_course_roster", self._course_roster_tool, kwargs)

    async def get_student_enrollments(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_student_enrollments", self._student_enrollments_tool, kwargs)

    async def get_enrollment(self, **kwargs: Any) -> ToolResponse:
        return await self._invoke_kwargs("get_enrollment", self._enrollment_tool, kwargs)

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

    @staticmethod
    async def _invoke_kwargs(
        tool_name: str,
        tool: SearchTool,
        kwargs: dict[str, Any],
    ) -> ToolResponse:
        response = await asyncio.to_thread(tool, **kwargs)
        if not isinstance(response, dict):
            raise AcademicToolGatewayError(
                tool_name,
                f"expected a dictionary response, got {type(response).__name__}",
            )
        return response
