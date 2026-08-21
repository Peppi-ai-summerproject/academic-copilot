from unittest.mock import Mock
from app.services.course_results_service import CourseResultsService

def _service(rows):
    records, courses, students = Mock(), Mock(), Mock()
    courses.get_by_code.return_value = {"id": 9, "course_code": "DII101"}
    students.get_by_id.return_value = {"id": 1, "name": "Elina"}
    records.list_course_result_view.return_value = rows
    records.list_student_result_view.return_value = rows
    return CourseResultsService(records, courses, students)

def test_course_results_preserve_no_result_and_filter():
    rows = [{"result_status": "PASSED"}, {"result_status": "FAILED"}, {"result_status": "NO_RESULT"}]
    assert _service(rows).course_results("DII101", "FAILED")["results"] == [rows[1]]

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
