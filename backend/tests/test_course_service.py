from unittest.mock import Mock

from app.services.course_service import CourseService


def test_get_course_by_code_is_exact_and_case_insensitive() -> None:
    repository = Mock()
    repository.get_by_code.return_value = {"id": 1, "course_code": "DIN007", "course_name": "Software Testing", "credits": 3}
    result = CourseService(repository).get_course(course_code=" din007 ")
    assert result["success"] is True
    assert result["course"]["course_code"] == "DIN007"
    repository.get_by_code.assert_called_once_with("din007")


def test_get_course_missing_and_invalid_identifier_are_machine_readable() -> None:
    repository = Mock()
    repository.get_by_id.return_value = None
    service = CourseService(repository)
    assert service.get_course(course_id=404)["error"] == "COURSE_NOT_FOUND"
    assert service.get_course()["error"] == "INVALID_COURSE_IDENTIFIER"


def test_search_courses_returns_multiple_candidates_and_empty_results() -> None:
    repository = Mock()
    repository.search.return_value = [{"id": 1}, {"id": 2}]
    result = CourseService(repository).search_courses("SOFTWARE")
    assert result["success"] is True
    assert result["pagination"]["total"] == 2
    repository.search.assert_called_once_with("SOFTWARE")
    repository.search.return_value = []
    assert CourseService(repository).search_courses("missing")["courses"] == []


def test_search_courses_rejects_invalid_query_and_page() -> None:
    service = CourseService(Mock())
    assert service.search_courses(query=42)["error"] == "INVALID_SEARCH_QUERY"
    assert service.search_courses(limit=0)["error"] == "INVALID_SEARCH_PARAMETERS"
