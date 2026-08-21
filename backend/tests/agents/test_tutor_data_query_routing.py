import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app.agents.intent_detection import detect_intent
from app.agents.state import create_initial_state
from app.agents.tutor_data_query_agent import TutorDataQueryAgent


@pytest.mark.parametrize(
    ("message", "capability", "parameters"),
    [
        ("Find Anna Korhonen.", "student_lookup", {}),
        ("Show me Aino Mäkinen.", "student_lookup", {}),
        ("Find student 202600123.", "student_lookup", {}),
        ("Find student S002.", "student_lookup", {}),
        ("How is Anna Korhonen progressing?", "student_progress", {}),
        ("What is DIN24?", "course_lookup", {}),
        ("Show me all courses.", "course_search", {}),
        ("Who is enrolled in DIN24?", "course_roster", {}),
        ("Which courses is Anna Korhonen enrolled in?", "student_enrollments", {}),
        ("Who passed DIN24?", "course_results", {"result_filter": "PASSED"}),
        ("Students who didn't pass DIN24", "course_results", {"result_filter": "FAILED"}),
        ("What is the pass rate for DIN24?", "course_analytics", {}),
        ("Did Anna Korhonen pass DIN24?", "student_course_result", {}),
        ("Find teacher Matti Virtanen.", "teacher_lookup", {}),
        ("What is Matti Virtanen's email?", "teacher_contact", {}),
        ("Who is responsible for DIN24?", "course_teachers", {"role": "LEAD_TEACHER"}),
        ("Which courses does Matti Virtanen teach?", "teacher_courses", {}),
        ("Show me DIN24.", "academic_lookup", {}),
        ("Which students are in DIN24?", "group_students", {}),
        ("Which courses does DIN24 have?", "group_courses", {}),
        ("Who teaches Database Systems for DIN24?", "group_course_teachers", {}),
    ],
)
def test_realistic_tutor_queries_map_to_capabilities(message, capability, parameters):
    result = detect_intent(message)
    assert result.intent == "academic_data"
    assert result.route == "academic_data"
    assert result.capability == capability
    assert result.parameters == parameters


def test_multi_entity_query_preserves_student_and_course_references():
    result = detect_intent("Did Anna Korhonen pass DIN24?")
    assert result.entity_references == (("STUDENT", "Anna Korhonen"), ("COURSE", "DIN24"))


def test_unicode_student_name_and_alphanumeric_number_are_preserved_for_resolution():
    by_name = detect_intent("Show me Aino Mäkinen.")
    by_decomposed_name = detect_intent("Show me Aino Ma\u0308kinen.")
    by_number = detect_intent("Find student S002.")

    assert by_name.entity_references == (("STUDENT", "Aino Mäkinen"),)
    assert by_decomposed_name.entity_references == (("STUDENT", "Aino Mäkinen"),)
    assert by_number.entity_references == (("STUDENT", "S002"),)


def _state(capability, entities, query_parameters=None):
    state = create_initial_state(user_message="query")
    state.parameters = {"capability": capability, "query_parameters": query_parameters or {}}
    state.resolved_entities = entities
    return state


def test_data_agent_executes_resolved_course_results_capability():
    gateway = Mock()
    gateway.get_course_results = AsyncMock(return_value={"success": True, "results": []})
    state = _state(
        "course_results",
        [{"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 4, "candidates": [{"course_code": "DIN24"}]}],
        {"result_filter": "FAILED"},
    )
    result = asyncio.run(TutorDataQueryAgent(gateway).run(state))
    assert result.status == "SUCCESS"
    gateway.get_course_results.assert_awaited_once_with(course_code="DIN24", status="FAILED")


def test_data_agent_executes_multi_entity_enrollment_capability():
    gateway = Mock()
    gateway.get_enrollment = AsyncMock(return_value={"success": True, "enrollment": {}})
    state = _state(
        "enrollment",
        [
            {"entity_type": "STUDENT", "status": "RESOLVED", "canonical_id": 7},
            {"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 4},
        ],
    )
    result = asyncio.run(TutorDataQueryAgent(gateway).run(state))
    assert result.status == "SUCCESS"
    gateway.get_enrollment.assert_awaited_once_with(student_id=7, course_id=4)


@pytest.mark.parametrize(
    ("result_status", "grade"),
    [("PASSED", 5), ("FAILED", 0)],
)
def test_student_course_yes_no_query_returns_actual_result_without_status_filter(
    result_status, grade
):
    gateway = Mock()
    gateway.get_student_results = AsyncMock(
        return_value={
            "success": True,
            "results": [
                {
                    "course_code": "DIN24",
                    "result_status": result_status,
                    "grade": grade,
                }
            ],
        }
    )
    state = _state(
        "student_course_result",
        [
            {"entity_type": "STUDENT", "status": "RESOLVED", "canonical_id": 7},
            {
                "entity_type": "COURSE",
                "status": "RESOLVED",
                "canonical_id": 24,
                "candidates": [{"course_code": "DIN24"}],
            },
        ],
        {"result_filter": "PASSED"},
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(state))

    assert result_status in result.summary
    assert f"grade {grade}" in result.summary
    gateway.get_student_results.assert_awaited_once_with(student_id=7)


def test_student_course_query_reports_none_only_when_course_result_is_absent():
    gateway = Mock()
    gateway.get_student_results = AsyncMock(
        return_value={
            "success": True,
            "results": [
                {"course_code": "MAT101", "result_status": "PASSED", "grade": 4}
            ],
        }
    )
    state = _state(
        "student_course_result",
        [
            {"entity_type": "STUDENT", "status": "RESOLVED", "canonical_id": 7},
            {
                "entity_type": "COURSE",
                "status": "RESOLVED",
                "canonical_id": 24,
                "candidates": [{"course_code": "DIN24"}],
            },
        ],
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(state))

    assert result.summary == "Results: none found."
    gateway.get_student_results.assert_awaited_once_with(student_id=7)


def test_course_search_renders_multiple_course_codes_and_names():
    gateway = Mock()
    gateway.search_courses = AsyncMock(
        return_value={
            "success": True,
            "pagination": {"returned": 2, "total": 2, "has_more": False},
            "courses": [
                {"course_code": "DIN24", "course_name": "Digital Innovation"},
                {"course_code": "MAT101", "course_name": "Mathematics"},
            ],
        }
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(_state("course_search", [])))

    assert result.status == "SUCCESS"
    assert "DIN24" in result.summary and "Digital Innovation" in result.summary
    assert "MAT101" in result.summary and "Mathematics" in result.summary
    assert "query completed" not in result.summary.lower()
    gateway.search_courses.assert_awaited_once_with()


def test_course_search_renders_clear_empty_result():
    gateway = Mock()
    gateway.search_courses = AsyncMock(
        return_value={
            "success": True,
            "pagination": {"returned": 0, "total": 0, "has_more": False},
            "courses": [],
        }
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(_state("course_search", [])))

    assert result.summary == "Courses: none found."


def test_course_search_discloses_when_more_paginated_results_exist():
    gateway = Mock()
    gateway.search_courses = AsyncMock(
        return_value={
            "success": True,
            "pagination": {"returned": 2, "total": 27, "has_more": True},
            "courses": [
                {"course_code": "DIN24", "course_name": "Digital Innovation"},
                {"course_code": "MAT101", "course_name": "Mathematics"},
            ],
        }
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(_state("course_search", [])))

    assert "Showing 2 of 27 courses on this page" in result.summary
    assert "more results are available" in result.summary


def test_course_lookup_rendering_remains_unchanged():
    gateway = Mock()
    gateway.get_course = AsyncMock(
        return_value={
            "success": True,
            "course": {
                "course_code": "DIN24",
                "course_name": "Digital Innovation",
                "credits": 5,
            },
        }
    )
    state = _state(
        "course_lookup",
        [{"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 24}],
    )

    result = asyncio.run(TutorDataQueryAgent(gateway).run(state))

    assert "Digital Innovation" in result.summary
    assert "course code: DIN24" in result.summary
    assert "credits: 5" in result.summary


def test_group_capabilities_render_canonical_content_and_validate_composition():
    gateway = Mock()
    gateway.get_student_group = AsyncMock(return_value={"success": True, "group": {"group_code": "DIN24", "group_name": "Digital Innovation", "programme_code": "DIN2024S"}})
    gateway.get_student_group_students = AsyncMock(return_value={"success": True, "group": {"group_code": "DIN24"}, "students": [{"student_number": "S002", "name": "Aino Mäkinen"}]})
    gateway.get_student_group_courses = AsyncMock(return_value={"success": True, "group": {"group_code": "DIN24"}, "courses": [{"id": 101, "course_code": "DII101", "course_name": "Database Systems"}]})
    gateway.get_course_teachers = AsyncMock(return_value={"success": True, "teachers": [{"display_name": "Matti Virtanen", "email": "matti@example.test"}]})
    group = {"entity_type": "STUDENT_GROUP", "status": "RESOLVED", "canonical_id": 24}
    course = {"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 101}

    lookup = asyncio.run(TutorDataQueryAgent(gateway).run(_state("group_lookup", [group])))
    students = asyncio.run(TutorDataQueryAgent(gateway).run(_state("group_students", [group])))
    courses = asyncio.run(TutorDataQueryAgent(gateway).run(_state("group_courses", [group])))
    teachers = asyncio.run(TutorDataQueryAgent(gateway).run(_state("group_course_teachers", [group, course])))

    assert "DIN24" in lookup.summary and "Digital Innovation" in lookup.summary
    assert "Aino Mäkinen" in students.summary
    assert "DII101" in courses.summary and "Database Systems" in courses.summary
    assert "Matti Virtanen" in teachers.summary
    assert "query completed" not in teachers.summary.lower()


def test_group_course_teacher_query_rejects_unassociated_course_without_teacher_call():
    gateway = Mock()
    gateway.get_student_group_courses = AsyncMock(return_value={"success": True, "courses": []})
    gateway.get_course_teachers = AsyncMock()
    entities = [
        {"entity_type": "STUDENT_GROUP", "status": "RESOLVED", "canonical_id": 24},
        {"entity_type": "COURSE", "status": "RESOLVED", "canonical_id": 999},
    ]
    result = asyncio.run(TutorDataQueryAgent(gateway).run(_state("group_course_teachers", entities)))
    assert "not associated" in result.summary
    gateway.get_course_teachers.assert_not_awaited()
