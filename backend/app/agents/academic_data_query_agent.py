"""Orchestrate structured tutor-data operations through the academic gateway."""
from __future__ import annotations
from typing import Any
from app.agents.state import AgentState
from app.agents.types import AgentResult
from app.gateways.academic_tools import AcademicToolGateway

class AcademicDataQueryAgent:
    name = "AcademicDataQueryAgent"
    description = "Retrieves authoritative tutor academic data through MCP tools."
    def __init__(self, gateway: AcademicToolGateway) -> None: self._gateway = gateway
    async def run(self, state: AgentState) -> AgentResult:
        operation = state.parameters.get("academic_operation")
        methods: dict[str, tuple[str, dict[str, Any]]] = {
            "course_results": ("get_course_results", state.parameters),
            "course_analytics": ("get_course_completion_analytics", state.parameters),
            "course_roster": ("get_course_roster", state.parameters),
            "student_enrollments": ("get_student_enrollments", {"student_id": state.student_id}),
        }
        if operation not in methods:
            return AgentResult(self.name, "academic_data", "FAILED", "Unsupported academic data operation.", errors=["UNSUPPORTED_OPERATION"])
        method, kwargs = methods[operation]
        kwargs = {key: value for key, value in kwargs.items() if key in {"course_code", "course_id", "student_id", "status", "enrollment_status"} and value is not None}
        if not kwargs:
            return AgentResult(self.name, "academic_data", "FAILED", "Required academic entity is missing.", errors=["MISSING_ENTITY"])
        response = await getattr(self._gateway, method)(**kwargs)
        if not isinstance(response, dict) or not response.get("success"):
            return AgentResult(self.name, "academic_data", "FAILED", "Academic data could not be retrieved.", data=response if isinstance(response, dict) else {}, errors=["TOOL_FAILURE"])
        return AgentResult(self.name, "academic_data", "SUCCESS", "Academic data retrieved.", data={"operation": operation, **response})
