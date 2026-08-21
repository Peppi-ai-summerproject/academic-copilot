from unittest.mock import Mock

from app.services.student_group_service import StudentGroupService


def test_service_exposes_lookup_students_courses_and_search_contracts():
    repository = Mock()
    group = {"id": 24, "group_code": "DIN24"}
    repository.search.return_value = [group]
    repository.get_by_id.return_value = group
    repository.list_students.return_value = [{"id": 2, "name": "Aino Mäkinen"}]
    repository.list_courses.return_value = [{"id": 101, "course_code": "DII101"}]
    service = StudentGroupService(repository)

    assert service.search_groups(" DIN24 ")["group_count"] == 1
    assert service.get_group(24)["group"] == group
    assert service.get_students(24)["student_count"] == 1
    assert service.get_courses(24)["course_count"] == 1
    repository.search.assert_called_once_with("DIN24")


def test_service_controls_invalid_and_missing_group_ids():
    repository = Mock()
    repository.get_by_id.return_value = None
    service = StudentGroupService(repository)
    assert service.get_group(0)["error"] == "INVALID_STUDENT_GROUP_ID"
    assert service.get_group(24)["error"] == "STUDENT_GROUP_NOT_FOUND"


def test_get_students_returns_group_students_and_count():
    repository = Mock()
    group = {"id": 24, "group_code": "DIN24"}
    students = [
        {"id": 1, "student_number": "S001", "name": "Mikael Virtanen"},
        {"id": 2, "student_number": "S002", "name": "Aino Mäkinen"},
    ]
    repository.get_by_id.return_value = group
    repository.list_students.return_value = students

    result = StudentGroupService(repository).get_students(24)

    assert result == {
        "success": True,
        "group": group,
        "students": students,
        "student_count": 2,
    }
    repository.get_by_id.assert_called_once_with(24)
    repository.list_students.assert_called_once_with(24)


def test_get_students_preserves_missing_group_error_without_listing_students():
    repository = Mock()
    repository.get_by_id.return_value = None

    result = StudentGroupService(repository).get_students(24)

    assert result == {"success": False, "error": "STUDENT_GROUP_NOT_FOUND"}
    repository.list_students.assert_not_called()


def test_get_students_controls_invalid_group_id_without_repository_access():
    repository = Mock()

    result = StudentGroupService(repository).get_students(0)

    assert result == {"success": False, "error": "INVALID_STUDENT_GROUP_ID"}
    repository.get_by_id.assert_not_called()
    repository.list_students.assert_not_called()
