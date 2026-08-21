from unittest.mock import Mock
from app.repositories.academic_record_repository import AcademicRecordRepository
from app.services.course_results_service import CourseResultsService

def _service(rows):
    records, courses, students = Mock(), Mock(), Mock()
    courses.get_by_code.return_value = {"id": 9, "course_code": "DII101"}
    students.get_by_id.return_value = {"id": 1, "name": "Elina"}
    records.list_course_result_view.return_value = rows
    records.list_results_for_course.side_effect = lambda _, result_status=None: [
        row for row in rows if row.get("result_status") == result_status
    ]
    records.list_student_result_view.return_value = rows
    return CourseResultsService(records, courses, students)

def test_course_results_preserve_no_result_and_filter():
    rows = [{"result_status": "PASSED"}, {"result_status": "FAILED"}, {"result_status": "NO_RESULT"}]
    assert _service(rows).course_results("DII101", "FAILED")["results"] == [rows[1]]

def test_pass_fail_filters_use_authoritative_completion_query():
    records, courses, students = Mock(), Mock(), Mock()
    courses.get_by_code.return_value = {"id": 25, "course_code": "DBS24"}
    failed = {"student_id": 41, "student_name": "Oskari Example", "result_status": "FAILED", "grade": "0"}
    records.list_results_for_course.return_value = [failed]
    service = CourseResultsService(records, courses, students)

    assert service.course_results("DBS24", "FAILED")["results"] == [failed]
    records.list_results_for_course.assert_called_once_with(25, result_status="FAILED")
    records.list_course_result_view.assert_not_called()

def test_failed_grade_zero_survives_real_repository_and_service_path():
    failed = {
        "id": 90,
        "student_id": 41,
        "student_number": "DEMO22102",
        "student_name": "Oskari Example",
        "course_id": 25,
        "course_code": "DBS24",
        "course_name": "Database Systems",
        "credits": 5,
        "semester": 2,
        "result_status": "FAILED",
        "grade": "0",
        "completion_date": "2025-06-10",
    }
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = [failed]
    courses, students = Mock(), Mock()
    courses.get_by_code.return_value = {"id": 25, "course_code": "DBS24"}
    service = CourseResultsService(AcademicRecordRepository(session), courses, students)

    result = service.course_results("DBS24", "FAILED")

    assert result["results"] == [failed]
    assert result["results"][0]["grade"] == "0"
    statement, params = session.execute.call_args.args
    assert "FROM course_completions AS completion" in statement.text
    assert "INNER JOIN students AS student" in statement.text
    assert "course_enrollments" not in statement.text
    assert params == {"entity_id": 25, "result_status": "FAILED"}

def test_analytics_uses_enrolled_denominator_and_safe_zero():
    rows = [{"result_status": "PASSED"}, {"result_status": "FAILED"}, {"result_status": "IN_PROGRESS"}, {"result_status": "NO_RESULT"}]
    analytics = _service(rows).analytics("DII101")["analytics"]
    assert (analytics["enrolled_count"], analytics["completed_count"], analytics["pass_rate"]) == (4, 2, 0.25)
    assert _service([]).analytics("DII101")["analytics"]["completion_rate"] == 0.0

def test_results_validate_identifiers_and_statuses():
    service = _service([])
    assert service.course_results("", None)["error"] == "INVALID_COURSE_CODE"
    assert service.course_results("DII101", "UNKNOWN")["error"] == "INVALID_RESULT_STATUS"
    assert service.student_results(0)["error"] == "INVALID_STUDENT_ID"
