from typing import Any

from app.repositories.study_right_repository import StudyRightRepository


class StudyRightService:
    """Business logic for retrieving study right information."""

    def __init__(self, repository: StudyRightRepository) -> None:
        self._repository = repository

    def get_study_right(self, student_id: int) -> dict[str, Any]:
        if student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }

        study_right = self._repository.get_by_student_id(student_id)

        if study_right is None:
            return {
                "success": False,
                "error": "STUDY_RIGHT_NOT_FOUND",
                "message": (
                    f"Study right for student with ID {student_id} "
                    "was not found."
                ),
            }

        is_expiring_soon = study_right["status"] == "EXPIRES_SOON"

        return {
            "success": True,
            "study_right": {
                **study_right,
                "expiration_date": study_right["end_date"],
                "is_expiring_soon": is_expiring_soon,
            },
        }