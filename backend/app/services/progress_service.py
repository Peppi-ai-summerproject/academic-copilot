from typing import Any

from app.repositories.progress_repository import ProgressRepository


class ProgressService:
    """Business logic for calculating academic progress."""

    def __init__(self, repository: ProgressRepository) -> None:
        self._repository = repository

    def get_progress(self, student_id: int) -> dict[str, Any]:
        if student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }

        progress_data = self._repository.get_student_progress_data(student_id)

        if progress_data is None:
            return {
                "success": False,
                "error": "STUDENT_NOT_FOUND",
                "message": f"Student with ID {student_id} was not found.",
            }

        programme = progress_data["programme"]
        current_semester = int(progress_data["current_semester"])
        completed_ects = int(progress_data["completed_ects"])

        expected_ects = self._repository.get_expected_ects(
            programme,
            current_semester,
        )

        if expected_ects is None:
            return {
                "success": False,
                "error": "CURRICULUM_NOT_FOUND",
                "message": (
                    f"Curriculum data was not found for programme "
                    f"'{programme}' and semester {current_semester}."
                ),
            }

        difference_ects = completed_ects - expected_ects
        remaining_to_expected_ects = max(expected_ects - completed_ects, 0)

        progress_percentage = (
            round((completed_ects / expected_ects) * 100, 2)
            if expected_ects > 0
            else 0.0
        )

        if completed_ects > expected_ects:
            status = "AHEAD"
        elif completed_ects == expected_ects:
            status = "ON_TRACK"
        else:
            status = "BEHIND"

        return {
            "success": True,
            "progress": {
                "student_id": progress_data["student_id"],
                "student_number": progress_data["student_number"],
                "student_name": progress_data["name"],
                "programme": programme,
                "current_semester": current_semester,
                "completed_ects": completed_ects,
                "expected_ects": expected_ects,
                "difference_ects": difference_ects,
                "remaining_to_expected_ects": remaining_to_expected_ects,
                "progress_percentage": progress_percentage,
                "status": status,
            },
        }