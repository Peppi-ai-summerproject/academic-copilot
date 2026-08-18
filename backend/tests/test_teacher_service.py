from unittest.mock import Mock

from app.services.teacher_service import TeacherService


def test_teacher_lookup_returns_supported_contact_data() -> None:
    repository = Mock()
    repository.get_by_id.return_value = {"id": 1, "name": "Anna Korhonen", "email": "anna@peppi.example", "role": "Lecturer"}
    result = TeacherService(repository).get_teacher(1)
    assert result["success"] is True
    assert result["teacher"]["email"] == "anna@peppi.example"


def test_teacher_lookup_not_found_and_invalid_id_are_machine_readable() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None
    service = TeacherService(repository)
    assert service.get_teacher(9)["error"] == "TEACHER_NOT_FOUND"
    assert service.get_teacher(0)["error"] == "INVALID_TEACHER_ID"


def test_teacher_search_is_case_insensitive_at_repository_boundary() -> None:
    repository = Mock()
    repository.search_teachers.return_value = ([{"id": 1, "name": "Anna Korhonen"}, {"id": 2, "name": "Mia Korhonen"}], 2)
    result = TeacherService(repository).search_teachers("Korhonen")
    assert result["pagination"]["total"] == 2
    repository.search_teachers.assert_called_once_with("Korhonen", 20, 0)
