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
        ("Did Anna Korhonen pass DIN24?", "student_course_result", {"result_filter": "PASSED"}),
        ("Find teacher Matti Virtanen.", "teacher_lookup", {}),
        ("What is Matti Virtanen's email?", "teacher_contact", {}),
        ("Who is responsible for DIN24?", "course_teachers", {"role": "LEAD_TEACHER"}),
        ("Which courses does Matti Virtanen teach?", "teacher_courses", {}),
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
