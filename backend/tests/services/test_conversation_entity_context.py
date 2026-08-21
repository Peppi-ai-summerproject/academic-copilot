from app.services.conversation_context import (
    canonical_entities,
    merge_canonical_entities,
    missing_entities,
)


def entity(kind, identifier, *, display_name=None, candidates=None, status="RESOLVED"):
    return {
        "entity_type": kind,
        "status": status,
        "canonical_id": identifier,
        "display_name": display_name,
        "candidates": candidates or [],
        "academic_record": {"grades": [5]},
    }


def test_creates_minimal_canonical_student_course_and_teacher_context():
    context = canonical_entities([
        entity("STUDENT", 1, display_name="Anna", candidates=[{"student_number": "S1", "programme": "ICT"}]),
        entity("COURSE", 2, display_name="Digital", candidates=[{"course_code": "DIN24", "roster": [1]}]),
        entity("TEACHER", 3, display_name="Matti", candidates=[{"email": "matti@example.test"}]),
    ])

    assert [row["canonical_id"] for row in context] == [1, 2, 3]
    assert context[0]["candidates"] == [{"student_number": "S1"}]
    assert context[1]["candidates"] == [{"course_code": "DIN24"}]
    assert "academic_record" not in repr(context)
    assert "email" not in repr(context)


def test_explicit_entity_switches_only_its_type_and_preserves_others():
    stored = [entity("STUDENT", 1), entity("COURSE", 2), entity("TEACHER", 3)]
    merged = merge_canonical_entities(stored, [entity("STUDENT", 9)])
    assert {row["entity_type"]: row["canonical_id"] for row in merged} == {
        "STUDENT": 9, "COURSE": 2, "TEACHER": 3,
    }


def test_unresolved_or_ambiguous_entities_never_replace_canonical_context():
    stored = [entity("COURSE", 2)]
    merged = merge_canonical_entities(stored, [
        entity("COURSE", None, status="NOT_FOUND"),
        entity("STUDENT", None, status="AMBIGUOUS"),
    ])
    assert [(row["entity_type"], row["canonical_id"]) for row in merged] == [("COURSE", 2)]


def test_capability_requirements_report_missing_context_without_guessing():
    assert missing_entities("student_course_result", []) == ("STUDENT", "COURSE")
    assert missing_entities("course_teachers", [entity("STUDENT", 1)]) == ("COURSE",)

