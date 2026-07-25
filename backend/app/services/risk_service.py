from datetime import date
from typing import Any

from app.repositories.risk_repository import RiskRepository


class RiskService:
    """Business logic for identifying students who may need tutor intervention."""

    def __init__(self, repository: RiskRepository) -> None:
        self._repository = repository

    def find_students_at_risk(
        self,
        programme_code: str | None = None,
    ) -> dict[str, Any]:
        students = self._repository.get_students_for_risk_analysis(
            programme_code=programme_code,
        )

        at_risk_students: list[dict[str, Any]] = []

        for student in students:
            risk_result = self._analyse_student(student)

            if risk_result["risk_level"] != "LOW":
                at_risk_students.append(risk_result)

        risk_counts = {
            "high": sum(
                1
                for student in at_risk_students
                if student["risk_level"] == "HIGH"
            ),
            "medium": sum(
                1
                for student in at_risk_students
                if student["risk_level"] == "MEDIUM"
            ),
        }

        return {
            "success": True,
            "filters": {
                "programme_code": programme_code,
            },
            "risk_summary": {
                "total_students_analysed": len(students),
                "total_at_risk": len(at_risk_students),
                "high_risk": risk_counts["high"],
                "medium_risk": risk_counts["medium"],
            },
            "students": at_risk_students,
        }

    def _analyse_student(
        self,
        student: dict[str, Any],
    ) -> dict[str, Any]:
        completed_ects = int(student["completed_ects"] or 0)
        expected_ects = int(student["expected_ects"] or 0)
        difference_ects = completed_ects - expected_ects

        study_right_status = (
            student.get("study_right_status") or "UNKNOWN"
        ).upper()

        risk_level = "LOW"
        risk_reasons: list[str] = []

        if difference_ects <= -60:
            risk_level = "HIGH"
            risk_reasons.append(
                f"Student is {abs(difference_ects)} ECTS "
                "behind expected progression."
            )
        elif difference_ects < 0:
            risk_level = "MEDIUM"
            risk_reasons.append(
                f"Student is {abs(difference_ects)} ECTS "
                "behind expected progression."
            )

        if study_right_status == "EXPIRED":
            risk_level = "HIGH"
            risk_reasons.append("Study right has expired.")

        elif study_right_status == "EXPIRES_SOON":
            if risk_level == "LOW":
                risk_level = "MEDIUM"

            risk_reasons.append("Study right expires soon.")

        elif study_right_status == "EXTENDED":
            if risk_level == "LOW":
                risk_level = "MEDIUM"

            risk_reasons.append("Study right has been extended.")

        return {
            "student_id": student["student_id"],
            "student_number": student["student_number"],
            "student_name": student["student_name"],
            "group_name": student.get("group_name"),
            "programme": student["programme"],
            "programme_code": student["programme_code"],
            "completed_ects": completed_ects,
            "expected_ects": expected_ects,
            "difference_ects": difference_ects,
            "current_semester": student["current_semester"],
            "study_right_status": study_right_status,
            "study_right_end_date": self._serialize_date(
                student.get("study_right_end_date")
            ),
            "extension_count": student.get("extension_count", 0),
            "risk_level": risk_level,
            "risk_reasons": risk_reasons,
        }

    @staticmethod
    def _serialize_date(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, date):
            return value.isoformat()

        return str(value)