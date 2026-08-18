from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session


ResultStatus = Literal["PASSED", "FAILED"]


class AcademicRecordRepository:
    """Read student-course enrollment and authoritative completion records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_courses_for_student(self, student_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT
                    course.id,
                    course.course_code,
                    course.course_name,
                    course.credits,
                    enrollment.enrollment_status,
                    enrollment.enrolled_at
                FROM course_enrollments AS enrollment
                INNER JOIN courses AS course ON course.id = enrollment.course_id
                WHERE enrollment.student_id = :student_id
                ORDER BY course.course_code ASC, course.id ASC
                """
            ),
            {"student_id": student_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_students_for_course(self, course_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(
            text(
                """
                SELECT
                    student.id,
                    student.student_number,
                    student.name,
                    student.email,
                    enrollment.enrollment_status
                FROM course_enrollments AS enrollment
                INNER JOIN students AS student ON student.id = enrollment.student_id
                WHERE enrollment.course_id = :course_id
                ORDER BY student.name ASC, student.student_number ASC, student.id ASC
                """
            ),
            {"course_id": course_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_results_for_student(
        self,
        student_id: int,
        *,
        result_status: ResultStatus | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_results(
            "completion.student_id = :entity_id",
            student_id,
            result_status,
        )

    def list_results_for_course(
        self,
        course_id: int,
        *,
        result_status: ResultStatus | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_results(
            "completion.course_id = :entity_id",
            course_id,
            result_status,
        )

    def _list_results(
        self,
        entity_clause: str,
        entity_id: int,
        result_status: ResultStatus | None,
    ) -> list[dict[str, Any]]:
        status_clause = ""
        parameters: dict[str, Any] = {"entity_id": entity_id}
        if result_status is not None:
            status_clause = "AND completion.result_status = :result_status"
            parameters["result_status"] = result_status
        rows = self._session.execute(
            text(
                f"""
                SELECT
                    completion.id,
                    completion.student_id,
                    completion.course_id,
                    course.course_code,
                    course.course_name,
                    completion.credits,
                    completion.semester,
                    completion.result_status,
                    completion.grade,
                    completion.completion_date
                FROM course_completions AS completion
                INNER JOIN courses AS course ON course.id = completion.course_id
                WHERE {entity_clause}
                  {status_clause}
                ORDER BY course.course_code ASC, completion.id ASC
                """
            ),
            parameters,
        ).mappings().all()
        return [dict(row) for row in rows]
