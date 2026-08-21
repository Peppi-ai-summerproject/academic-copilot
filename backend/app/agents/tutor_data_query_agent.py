"""Execute resolved tutor academic-data capabilities through the gateway."""

from __future__ import annotations

from collections.abc import Callable
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
    if capability == "student_lookup":
        student = response.get("student", {})
        return _profile(
            student.get("name", "Student"),
            ("student number", student.get("student_number")),
            ("email", student.get("email")),
            ("programme", student.get("programme")),
        )
    if capability == "course_lookup":
        course = response.get("course", {})
        return _profile(
            course.get("course_name") or course.get("name") or "Course",
            ("course code", course.get("course_code")),
            ("credits", course.get("credits") or course.get("ects")),
        )
    if capability == "teacher_lookup" or capability == "teacher_contact":
        teacher = response.get("teacher", {})
        return _profile(
            teacher.get("display_name") or teacher.get("name") or "Teacher",
            ("email", teacher.get("email")),
        )
    if capability == "course_roster":
        return _rows(
            "Enrolled students", response.get("students", []), _student_label
        )
    if capability == "student_enrollments":
        return _rows("Courses", response.get("enrollments", []), _course_label)
    if capability == "enrollment":
        enrollment = response.get("enrollment", {})
        status = (
            enrollment.get("status")
            or enrollment.get("enrollment_status")
            or "recorded"
        )
        return f"Enrollment status: {status}."
    if capability in {"course_results", "student_course_result"}:
        return _rows("Results", response.get("results", []), _result_label)
    if capability == "course_analytics":
        analytics = response.get("analytics", {})
        pass_rate = analytics.get("pass_rate")
        completion_rate = analytics.get("completion_rate")
        parts = []
        if isinstance(pass_rate, (int, float)):
            parts.append(f"pass rate {pass_rate * 100:.1f}%")
        if isinstance(completion_rate, (int, float)):
            parts.append(f"completion rate {completion_rate * 100:.1f}%")
        if analytics.get("enrolled_count") is not None:
            parts.append(f"{analytics['enrolled_count']} enrolled")
        return "Course analytics: " + ", ".join(parts) + "."
    if capability == "course_teachers":
        return _rows("Teachers", response.get("teachers", []), _teacher_label)
    if capability == "teacher_courses":
        rows = response.get("courses", response.get("assignments", []))
        return _rows("Teaching assignments", rows, _course_label)
    return f"Academic {capability.replace('_', ' ')} query completed."


def _profile(name: Any, *fields: tuple[str, Any]) -> str:
    details = [
        f"{label}: {value}" for label, value in fields if value not in (None, "")
    ]
    return f"{name}" + (f" — {', '.join(details)}." if details else ".")


def _rows(
    title: str,
    rows: Any,
    formatter: Callable[[dict[str, Any]], str],
) -> str:
    if not isinstance(rows, list) or not rows:
        return f"{title}: none found."
    labels = [formatter(row) for row in rows if isinstance(row, dict)]
    return f"{title}: " + "; ".join(labels) + "."


def _student_label(row: dict[str, Any]) -> str:
    return str(
        row.get("name")
        or row.get("student_name")
        or row.get("student_number")
        or "Student"
    )


def _course_label(row: dict[str, Any]) -> str:
    code = row.get("course_code")
    name = row.get("course_name") or row.get("name")
    return " — ".join(str(value) for value in (code, name) if value) or "Course"


def _teacher_label(row: dict[str, Any]) -> str:
    name = row.get("display_name") or row.get("name") or "Teacher"
    email = row.get("email")
    return f"{name} ({email})" if email else str(name)


def _result_label(row: dict[str, Any]) -> str:
    subject = row.get("student_name") or row.get("course_code") or "Result"
    status = row.get("result_status") or row.get("status")
    grade = row.get("grade")
    details = [
        str(value)
        for value in (
            status,
            f"grade {grade}" if grade is not None else None,
        )
        if value
    ]
    return f"{subject}: " + ", ".join(details)
