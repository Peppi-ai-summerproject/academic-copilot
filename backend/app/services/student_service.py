from typing import Any

from app.repositories.student_repository import StudentRepository


class StudentService:
    """Business logic for retrieving student information."""

    def __init__(self, repository: StudentRepository) -> None:
        self._repository = repository

    def get_student(self, student_id: int) -> dict[str, Any]:
        """Return a student profile or a structured missing-record response."""

        if student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }

        student = self._repository.get_by_id(student_id)

        if student is None:
            return {
                "success": False,
                "error": "STUDENT_NOT_FOUND",
                "message": f"Student with ID {student_id} was not found.",
            }

        return {
            "success": True,
            "student": student,
        }

    def get_student_by_number(self, student_number: str) -> dict[str, Any]:
        """Return a student by their exact academic identifier."""
        if not isinstance(student_number, str) or not student_number.strip():
            return {
                "success": False,
                "error": "INVALID_STUDENT_NUMBER",
                "message": "Student number must be a non-empty string.",
            }

        student = self._repository.get_by_student_number(student_number.strip())
        if student is None:
            return {
                "success": False,
                "error": "STUDENT_NOT_FOUND",
                "message": "Student with this student number was not found.",
            }
        return {"success": True, "student": student}
