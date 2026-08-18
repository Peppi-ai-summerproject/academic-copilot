from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session


ResultStatus = Literal["PASSED", "FAILED"]
EnrollmentStatus = Literal["ENROLLED", "IN_PROGRESS", "COMPLETED", "WITHDRAWN"]


class AcademicRecordRepository:
    """Read student-course enrollment and authoritative completion records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_courses_for_student(
        self,
        student_id: int,
        *,
        enrollment_status: EnrollmentStatus | None = None,
    ) -> list[dict[str, Any]]:
        status_clause = ""
        parameters: dict[str, Any] = {"student_id": student_id}
        if enrollment_status is not None:
            status_clause = "AND enrollment.enrollment_status = :enrollment_status"
            parameters["enrollment_status"] = enrollment_status
        rows = self._session.execute(
            text(
                f"""
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
                  {status_clause}
                ORDER BY course.course_code ASC, course.id ASC
                """
            ),
            parameters,
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_students_for_course(
        self,
        course_id: int,
        *,
        enrollment_status: EnrollmentStatus | None = None,
    ) -> list[dict[str, Any]]:
        status_clause = ""
        parameters: dict[str, Any] = {"course_id": course_id}
        if enrollment_status is not None:
            status_clause = "AND enrollment.enrollment_status = :enrollment_status"
            parameters["enrollment_status"] = enrollment_status
        rows = self._session.execute(
            text(
                f"""
                SELECT
                    student.id,
                    student.student_number,
                    student.name,
                    student.email,
                    student.programme,
                    student.status AS student_status,
                    enrollment.enrollment_status,
                    enrollment.enrolled_at
                FROM course_enrollments AS enrollment
                INNER JOIN students AS student ON student.id = enrollment.student_id
                WHERE enrollment.course_id = :course_id
                  {status_clause}
                ORDER BY student.name ASC, student.student_number ASC, student.id ASC
                """
            ),
            parameters,
        ).mappings().all()
        return [dict(row) for row in rows]

    def get_enrollment(
        self,
        student_id: int,
        course_id: int,
    ) -> dict[str, Any] | None:
        row = self._session.execute(
            text(
                """
                SELECT
                    enrollment.id AS enrollment_id,
                    enrollment.student_id,
                    student.student_number,
                    student.name AS student_name,
                    enrollment.course_id,
                    course.course_code,
                    course.course_name,
                    course.credits,
                    enrollment.enrollment_status,
                    enrollment.enrolled_at
                FROM course_enrollments AS enrollment
                INNER JOIN students AS student ON student.id = enrollment.student_id
                INNER JOIN courses AS course ON course.id = enrollment.course_id
                WHERE enrollment.student_id = :student_id
                  AND enrollment.course_id = :course_id
                """
            ),
            {"student_id": student_id, "course_id": course_id},
        ).mappings().first()
        return dict(row) if row is not None else None

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

    def list_course_result_view(self, course_id: int) -> list[dict[str, Any]]:
        """Return every enrollment once, including those with no completion."""
        return self._list_result_view("enrollment.course_id = :entity_id", course_id)

    def list_student_result_view(self, student_id: int) -> list[dict[str, Any]]:
        """Return every enrolled course once, including unfinished work."""
        return self._list_result_view("enrollment.student_id = :entity_id", student_id)

    def _list_result_view(self, clause: str, entity_id: int) -> list[dict[str, Any]]:
        rows = self._session.execute(text(f"""
            SELECT student.id AS student_id, student.student_number,
                   student.name AS student_name, course.id AS course_id,
                   course.course_code, course.course_name, completion.credits,
                   completion.grade, completion.completion_date,
                   CASE WHEN completion.result_status IS NOT NULL THEN completion.result_status
                        WHEN enrollment.enrollment_status = 'IN_PROGRESS' THEN 'IN_PROGRESS'
                        ELSE 'NO_RESULT' END AS result_status
            FROM course_enrollments AS enrollment
            INNER JOIN students AS student ON student.id = enrollment.student_id
            INNER JOIN courses AS course ON course.id = enrollment.course_id
            LEFT JOIN course_completions AS completion
              ON completion.student_id = enrollment.student_id
             AND completion.course_id = enrollment.course_id
            WHERE {clause}
            ORDER BY course.course_code ASC, student.name ASC, student.id ASC
        """), {"entity_id": entity_id}).mappings().all()
        return [dict(row) for row in rows]

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
