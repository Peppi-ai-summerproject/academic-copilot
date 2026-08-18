"""Execute resolved tutor academic-data capabilities through the gateway."""

from __future__ import annotations

from typing import Any

from app.agents.state import AgentState
from app.agents.types import AgentResult
from app.gateways.academic_tools import AcademicToolGateway


class TutorDataQueryAgent:
    name = "TutorDataQueryAgent"
    description = "Executes resolved student, course, result, and teacher queries."

    def __init__(self, gateway: AcademicToolGateway) -> None:
        self._gateway = gateway

    async def run(self, state: AgentState) -> AgentResult:
        capability = str(state.parameters.get("capability") or "")
        parameters = dict(state.parameters.get("query_parameters") or {})
        student = _entity(state, "STUDENT")
        course = _entity(state, "COURSE")
        teacher = _entity(state, "TEACHER")
        try:
            response = await self._execute(capability, parameters, student, course, teacher)
        except Exception:
            return AgentResult(self.name, "academic_data", "FAILED", "Academic data could not be retrieved.", errors=["ACADEMIC_DATA_TOOL_ERROR"])
        if not response.get("success"):
            error = str(response.get("error") or "ACADEMIC_DATA_UNAVAILABLE")
            return AgentResult(self.name, "academic_data", "FAILED", "Academic data could not be retrieved.", data=response, errors=[error])
        return AgentResult(
            self.name,
            "academic_data",
            "SUCCESS",
            _summary(capability, response),
            data={"capability": capability, "result": response},
        )

    async def _execute(self, capability: str, params: dict[str, Any], student, course, teacher):
        if capability == "student_lookup": return await self._gateway.get_student(student["canonical_id"])
        if capability == "student_progress": return await self._gateway.get_progress(student["canonical_id"])
        if capability == "course_search": return await self._gateway.search_courses()
        if capability == "course_lookup": return await self._gateway.get_course(course_id=course["canonical_id"])
        if capability == "course_roster": return await self._gateway.get_course_roster(course_id=course["canonical_id"])
        if capability == "student_enrollments": return await self._gateway.get_student_enrollments(student_id=student["canonical_id"])
        if capability == "enrollment": return await self._gateway.get_enrollment(student_id=student["canonical_id"], course_id=course["canonical_id"])
        if capability == "course_results": return await self._gateway.get_course_results(course_code=_course_code(course), status=params.get("result_filter"))
        if capability == "course_analytics": return await self._gateway.get_course_completion_analytics(course_code=_course_code(course))
        if capability == "student_course_result":
            result = await self._gateway.get_student_results(student_id=student["canonical_id"], status=params.get("result_filter"))
            if result.get("success"):
                rows = result.get("results", result.get("courses", []))
                result = {**result, "results": [row for row in rows if row.get("course_code") == _course_code(course)]}
            return result
        if capability in {"teacher_lookup", "teacher_contact"}: return await self._gateway.get_teacher(teacher["canonical_id"])
        if capability == "course_teachers": return await self._gateway.get_course_teachers(course_id=course["canonical_id"], role=params.get("role"))
        if capability == "teacher_courses": return await self._gateway.get_teacher_courses(teacher_id=teacher["canonical_id"])
        return {"success": False, "error": "UNSUPPORTED_TUTOR_QUERY"}


def _entity(state: AgentState, kind: str) -> dict[str, Any] | None:
    return next((row for row in state.resolved_entities if row.get("entity_type") == kind and row.get("status") == "RESOLVED"), None)


def _course_code(course: dict[str, Any]) -> str:
    candidates = course.get("candidates") or []
    return str(candidates[0].get("course_code") if candidates else course.get("display_name"))


def _summary(capability: str, response: dict[str, Any]) -> str:
    counts = ("student_count", "teacher_count", "assignment_count", "course_count")
    detail = next((f" ({response[key]})" for key in counts if key in response), "")
    return f"Academic {capability.replace('_', ' ')} query completed{detail}."
