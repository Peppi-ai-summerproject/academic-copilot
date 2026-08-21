from unittest.mock import Mock, patch

from app.mcp.tools import student_groups


def test_mcp_group_tools_use_service_contract_and_close_session():
    session = Mock()
    service = Mock()
    service.search_groups.return_value = {"success": True, "groups": []}
    service.get_group.return_value = {"success": True, "group": {"id": 24}}
    service.get_students.return_value = {"success": True, "students": []}
    service.get_courses.return_value = {"success": True, "courses": []}
    with patch.object(student_groups, "SessionLocal", return_value=session), patch.object(student_groups, "_service", return_value=service):
        assert student_groups.search_student_groups("DIN24")["success"]
        assert student_groups.get_student_group(24)["success"]
        assert student_groups.get_student_group_students(24)["success"]
        assert student_groups.get_student_group_courses(24)["success"]
    assert session.close.call_count == 4


def test_mcp_group_tool_returns_controlled_database_error():
    session = Mock()
    with patch.object(student_groups, "SessionLocal", return_value=session), patch.object(student_groups, "_service", side_effect=RuntimeError("db")):
        result = student_groups.search_student_groups("DIN24")
    assert result["error"] == "DATABASE_ERROR"
    session.close.assert_called_once_with()


def test_mcp_get_group_students_invokes_real_service_contract():
    session = Mock()
    repository = Mock()
    group = {"id": 24, "group_code": "DIN24"}
    students = [{"id": 2, "student_number": "S002", "name": "Aino Mäkinen"}]
    repository.get_by_id.return_value = group
    repository.list_students.return_value = students

    with patch.object(student_groups, "SessionLocal", return_value=session), patch.object(
        student_groups, "StudentGroupRepository", return_value=repository
    ):
        result = student_groups.get_student_group_students(24)

    assert result == {
        "success": True,
        "group": group,
        "students": students,
        "student_count": 1,
    }
    repository.get_by_id.assert_called_once_with(24)
    repository.list_students.assert_called_once_with(24)
    session.close.assert_called_once_with()
