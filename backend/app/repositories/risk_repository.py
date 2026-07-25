from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class RiskRepository:
    """Database access layer for academic risk detection."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_students_for_risk_analysis(
        self,
        programme_code: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT
                s.id AS student_id,
                s.student_number,
                s.name AS student_name,
                s.group_name,
                s.programme,
                s.programme_code,
                s.status AS student_status,

                COALESCE(SUM(cc.credits), 0) AS completed_ects,
                COALESCE(MAX(cc.semester), 1) AS current_semester,

                c.expected_ects,

                sr.status AS study_right_status,
                sr.start_date AS study_right_start_date,
                sr.end_date AS study_right_end_date,
                sr.extension_count

            FROM students s

            LEFT JOIN course_completions cc
                ON cc.student_id = s.id

            LEFT JOIN study_rights sr
                ON sr.student_id = s.id

            LEFT JOIN curriculum c
                ON c.programme = s.programme_code
                AND c.semester = (
                    SELECT COALESCE(MAX(cc2.semester), 1)
                    FROM course_completions cc2
                    WHERE cc2.student_id = s.id
                )

            WHERE 1 = 1
        """

        parameters: dict[str, Any] = {}

        if programme_code is not None:
            query += " AND s.programme_code = :programme_code"
            parameters["programme_code"] = programme_code

        query += """
            GROUP BY
                s.id,
                s.student_number,
                s.name,
                s.group_name,
                s.programme,
                s.programme_code,
                s.status,
                c.expected_ects,
                sr.status,
                sr.start_date,
                sr.end_date,
                sr.extension_count

            ORDER BY s.id
        """

        rows = (
            self._session.execute(
                text(query),
                parameters,
            )
            .mappings()
            .all()
        )

        return [dict(row) for row in rows]