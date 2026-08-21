"""Application-level validation for Epic #220 / Issue #235."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.agents.workflow import create_academic_agent_workflow, create_default_agent_registry
from app.schemas.chat import ChatRequest
from app.services.academic_entity_resolver import AcademicEntityResolver
from app.services.chat_service import ChatService
from app.services.conversation_memory import InMemoryConversationMemoryStore, MemoryScope
from app.services.session_service import SessionService
from app.telegram import handlers


class DeterministicAcademicGateway:
    """In-memory academic-data boundary; all application layers above it are real."""

    students = [
        {"id": 7, "student_number": "1234567", "name": "Anna Korhonen", "email": "anna@example.test", "programme": "ICT"},
        {"id": 8, "student_number": "7654321", "name": "John Smith", "email": "john@example.test", "programme": "ICT"},
        {"id": 9, "student_number": "1111111", "name": "Anna Laine", "email": "laine@example.test", "programme": "Business"},
        {"id": 1, "student_number": "S001", "name": "Mikael Virtanen", "email": "mikael@example.test", "programme": "ICT"},
        {"id": 2, "student_number": "S002", "name": "Aino Mäkinen", "email": "aino@example.test", "programme": "ICT"},
        {"id": 40, "student_number": "DEMO22101", "name": "Elina Demo", "email": "elina@example.test", "programme": "ICT"},
        {"id": 41, "student_number": "DEMO22102", "name": "Oskari Example", "email": "oskari@example.test", "programme": "ICT"},
        {"id": 42, "student_number": "DEMO22103", "name": "Sofia Sample", "email": "sofia@example.test", "programme": "ICT"},
    ]
    courses = [
        {"id": 24, "course_code": "DII101", "course_name": "Digital Innovation Foundations", "credits": 5},
        {"id": 25, "course_code": "DBS24", "course_name": "Database Systems", "credits": 5},
        {"id": 26, "course_code": "WEB24", "course_name": "Web Development", "credits": 5},
        {"id": 103, "course_code": "DE103", "course_name": "Database Systems", "credits": 5},
        {"id": 101, "course_code": "MAT101", "course_name": "Mathematics", "credits": 5},
        {"id": 202, "course_code": "SWE20", "course_name": "Software Engineering", "credits": 5},
    ]
    groups = [
        {"id": 240, "group_code": "DIN24", "group_name": "Digital Innovation 2024", "programme_code": "DIN2024S", "programme_name": "Business IT"},
        {"id": 241, "group_code": "BIT24", "group_name": "Business IT 2024", "programme_code": "BIT2024S", "programme_name": "Business IT"},
        {"id": 242, "group_code": "DUP24A", "group_name": "Shared cohort", "programme_code": "DIN2024S", "programme_name": "Business IT"},
        {"id": 243, "group_code": "DUP24B", "group_name": "Shared cohort", "programme_code": "BIT2024S", "programme_name": "Business IT"},
    ]
    teachers = [
        {"id": 31, "display_name": "Matti Virtanen", "email": "matti@example.test"},
        {"id": 32, "display_name": "Alex North", "email": "alex.n@example.test"},
        {"id": 33, "display_name": "Alex South", "email": "alex.s@example.test"},
        {"id": 34, "display_name": "Anna Example", "email": "anna.teacher@example.test"},
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _record(self, name: str, **kwargs):
        self.calls.append((name, kwargs))

    @staticmethod
    def _matches(rows, query, *fields):
        needle = str(query).casefold().removeprefix("the ").strip()
        return [row for row in rows if any(needle in str(row.get(field, "")).casefold() for field in fields)]

    async def search_students(self, **kwargs):
        self._record("search_students", **kwargs)
        return {"success": True, "students": deepcopy(self._matches(self.students, kwargs.get("query"), "student_number", "name"))}

    async def search_courses(self, **kwargs):
        self._record("search_courses", **kwargs)
        query = kwargs.get("query")
        rows = self.courses if query is None else self._matches(self.courses, query, "course_code", "course_name")
        return {
            "success": True,
            "pagination": {
                "returned": len(rows),
                "total": len(rows),
                "has_more": False,
            },
            "courses": deepcopy(rows),
        }

    async def search_teachers(self, **kwargs):
        self._record("search_teachers", **kwargs)
        return {"success": True, "teachers": deepcopy(self._matches(self.teachers, kwargs.get("query"), "display_name"))}

    async def search_student_groups(self, **kwargs):
        self._record("search_student_groups", **kwargs)
        query = kwargs.get("query")
        rows = self.groups if query is None else self._matches(self.groups, query, "group_code", "group_name")
        return {"success": True, "groups": deepcopy(rows)}

    async def get_student(self, student_id):
        self._record("get_student", student_id=student_id)
        row = next((row for row in self.students if row["id"] == student_id), None)
        return {"success": bool(row), "student": deepcopy(row)} if row else {"success": False, "error": "STUDENT_NOT_FOUND"}

    async def get_course(self, **kwargs):
        self._record("get_course", **kwargs)
        row = next((row for row in self.courses if row["id"] == kwargs.get("course_id")), None)
        return {"success": bool(row), "course": deepcopy(row)} if row else {"success": False, "error": "COURSE_NOT_FOUND"}

    async def get_teacher(self, teacher_id):
        self._record("get_teacher", teacher_id=teacher_id)
        row = next((row for row in self.teachers if row["id"] == teacher_id), None)
        return {"success": bool(row), "teacher": deepcopy(row)} if row else {"success": False, "error": "TEACHER_NOT_FOUND"}

    async def get_student_group(self, group_id):
        self._record("get_student_group", group_id=group_id)
        row = next((row for row in self.groups if row["id"] == group_id), None)
        return {"success": bool(row), "group": deepcopy(row)} if row else {"success": False, "error": "STUDENT_GROUP_NOT_FOUND"}

    async def get_student_group_students(self, group_id):
        self._record("get_student_group_students", group_id=group_id)
        group = next((row for row in self.groups if row["id"] == group_id), None)
        rows = self.students[5:8] if group_id == 240 else self.students[:2]
        return {"success": True, "group": deepcopy(group), "students": deepcopy(rows)}

    async def get_student_group_courses(self, group_id):
        self._record("get_student_group_courses", group_id=group_id)
        group = next((row for row in self.groups if row["id"] == group_id), None)
        rows = self.courses[:3] if group_id == 240 else self.courses[4:]
        return {"success": True, "group": deepcopy(group), "courses": deepcopy(rows)}

    async def get_course_roster(self, **kwargs):
        self._record("get_course_roster", **kwargs)
        return {"success": True, "students": deepcopy(self.students[:2]), "student_count": 2}

    async def get_student_enrollments(self, **kwargs):
        self._record("get_student_enrollments", **kwargs)
        return {"success": True, "enrollments": deepcopy(self.courses[:2])}

    async def get_enrollment(self, **kwargs):
        self._record("get_enrollment", **kwargs)
        return {"success": True, "enrollment": {"student_id": kwargs["student_id"], "course_id": kwargs["course_id"], "status": "ENROLLED"}}

    async def get_course_results(self, **kwargs):
        self._record("get_course_results", **kwargs)
        elina_grade = 4 if kwargs["course_code"] == "DBS24" else 5
        rows = [
            {"student_id": 7, "student_name": "Anna Korhonen", "course_code": kwargs["course_code"], "result_status": "PASSED", "grade": 4},
            {"student_id": 8, "student_name": "John Smith", "course_code": kwargs["course_code"], "result_status": "FAILED", "grade": 1},
            {"student_id": 40, "student_name": "Elina Demo", "course_code": kwargs["course_code"], "result_status": "PASSED", "grade": elina_grade},
            {"student_id": 41, "student_name": "Oskari Example", "course_code": kwargs["course_code"], "result_status": "FAILED", "grade": 0},
        ]
        if kwargs.get("status"):
            rows = [row for row in rows if row["result_status"] == kwargs["status"]]
        return {"success": True, "results": rows}

    async def get_student_results(self, **kwargs):
        self._record("get_student_results", **kwargs)
        rows_by_student = {
            40: [
                {"student_name": "Elina Demo", "course_code": "DII101", "result_status": "PASSED", "grade": 5},
                {"student_name": "Elina Demo", "course_code": "DBS24", "result_status": "PASSED", "grade": 4},
            ],
            41: [
                {"student_name": "Oskari Example", "course_code": "DII101", "result_status": "FAILED", "grade": 0},
                {"student_name": "Oskari Example", "course_code": "DBS24", "result_status": "FAILED", "grade": 0},
            ],
            42: [{"student_name": "Sofia Sample", "course_code": "MAT101", "result_status": "PASSED", "grade": 4}],
        }
        rows = rows_by_student.get(
            kwargs["student_id"],
            [
                {"course_code": "DII101", "result_status": "PASSED", "grade": 5},
                {"course_code": "MAT101", "result_status": "FAILED", "grade": 0},
            ],
        )
        if kwargs.get("status"):
            rows = [row for row in rows if row["result_status"] == kwargs["status"]]
        return {"success": True, "results": rows}

    async def get_course_completion_analytics(self, **kwargs):
        self._record("get_course_completion_analytics", **kwargs)
        rate = 0.5 if kwargs["course_code"] == "DII101" else 0.25
        return {"success": True, "analytics": {"enrolled_count": 4, "completed_count": 2, "pass_rate": rate, "completion_rate": 0.5}}

    async def get_course_teachers(self, **kwargs):
        self._record("get_course_teachers", **kwargs)
        return {"success": True, "teachers": [deepcopy(self.teachers[0])]}

    async def get_teacher_courses(self, **kwargs):
        self._record("get_teacher_courses", **kwargs)
        return {"success": True, "courses": [deepcopy(self.courses[0])]}

    async def get_progress(self, student_id):
        self._record("get_progress", student_id=student_id)
        return {"success": True, "progress": {"completed_ects": 55 if student_id == 7 else 30, "expected_ects": 60, "difference_ects": -5 if student_id == 7 else -30, "status": "BEHIND", "current_semester": 2, "progress_percentage": 91.7 if student_id == 7 else 50.0}}

    async def get_study_right(self, student_id):
        self._record("get_study_right", student_id=student_id)
        return {"success": True, "study_right": {"status": "ACTIVE", "extension_count": 0, "is_expiring_soon": False, "expiration_date": "2028-05-31"}}

    async def get_upcoming_events(self):
        self._record("get_upcoming_events")
        return {"success": True, "events": []}


@pytest.fixture
def copilot():
    gateway = DeterministicAcademicGateway()
    registry = create_default_agent_registry()
    memory = InMemoryConversationMemoryStore()
    service = ChatService(
        session_service=SessionService(),
        workflow=create_academic_agent_workflow(registry=registry, gateway=gateway),
        memory_store=memory,
        registry=registry,
        entity_resolver=AcademicEntityResolver(gateway),
    )
    return service, gateway, memory


def ask(copilot, message, *, user=100, chat=200):
    service, _, _ = copilot
    request = ChatRequest(message=message, telegram_user_id=user, telegram_chat_id=chat)
    return asyncio.run(service.process_message(request, trusted_telegram=True))


def active_entities(copilot, *, user=100, chat=200):
    _, _, memory = copilot
    conversation = memory.resolve_telegram_conversation(user, chat)
    scope = MemoryScope(conversation, "telegram", f"user:{user}:chat:{chat}", None)
    return {row["entity_type"]: row for row in memory.load(scope).resolved_entities}


@pytest.mark.e2e
def test_student_discovery_number_contact_and_minimal_context(copilot):
    assert "Anna Korhonen" in ask(copilot, "Find Anna Korhonen.").reply
    assert "1234567" in ask(copilot, "Find student 1234567.").reply
    assert "anna@example.test" in ask(copilot, "What is her email?").reply
    context = active_entities(copilot)["STUDENT"]
    assert context["canonical_id"] == 7
    assert "email" not in repr(context) and "programme" not in repr(context)


@pytest.mark.e2e
def test_unicode_student_lookup_replaces_active_student_for_progress(copilot):
    assert "Mikael Virtanen" in ask(copilot, "Show me Mikael Virtanen.").reply
    assert "Mikael Virtanen" in ask(copilot, "How is he progressing?").reply

    lookup = ask(copilot, "Show me Aino Mäkinen.").reply
    progress = ask(copilot, "How is she progressing?").reply

    assert "Aino Mäkinen" in lookup
    assert "Aino Mäkinen" in progress
    assert "Mikael Virtanen" not in progress
    assert active_entities(copilot)["STUDENT"]["canonical_id"] == 2


@pytest.mark.e2e
def test_alphanumeric_student_number_resolves_canonical_student(copilot):
    reply = ask(copilot, "Find student S002.").reply

    assert "Aino Mäkinen" in reply
    assert "S002" in reply
    assert active_entities(copilot)["STUDENT"]["canonical_id"] == 2


@pytest.mark.e2e
def test_failed_or_ambiguous_switch_keeps_previous_canonical_student(copilot):
    ask(copilot, "Show me Mikael Virtanen.")

    assert "could not find" in ask(copilot, "Show me Nobody Missing.").reply
    assert "Mikael Virtanen" in ask(copilot, "How is he progressing?").reply
    assert "multiple matching students" in ask(copilot, "Find Anna.").reply
    assert "Mikael Virtanen" in ask(copilot, "How is he progressing?").reply
    assert active_entities(copilot)["STUDENT"]["canonical_id"] == 1


@pytest.mark.e2e
def test_course_discovery_by_code_and_name(copilot):
    assert "DII101" in ask(copilot, "Show me DII101.").reply
    assert "Software Engineering" in ask(copilot, "Show me Software Engineering.").reply
    assert "Software Engineering" in ask(copilot, "Find the Software Engineering course.").reply
    assert active_entities(copilot)["COURSE"]["canonical_id"] == 202


@pytest.mark.e2e
def test_course_catalogue_response_contains_meaningful_course_content(copilot):
    reply = ask(copilot, "Show me all courses.").reply

    assert "DII101" in reply and "Digital Innovation Foundations" in reply
    assert "DBS24" in reply and "Database Systems" in reply
    assert "MAT101" in reply and "Mathematics" in reply
    assert "Academic course search query completed" not in reply


@pytest.mark.e2e
def test_student_group_lookup_lists_students_and_courses_with_context(copilot):
    assert "DIN24" in ask(copilot, "Show me DIN24.").reply
    courses = ask(copilot, "Which courses does it have?").reply
    students = ask(copilot, "Which students are in it?").reply

    assert "DII101" in courses and "Digital Innovation Foundations" in courses
    assert "DBS24" in courses and "Database Systems" in courses
    assert "WEB24" in courses and "Web Development" in courses
    assert "DIN24 —" not in courses
    assert "Elina Demo" in students and "Oskari Example" in students
    assert active_entities(copilot)["STUDENT_GROUP"]["canonical_id"] == 240
    assert "COURSE" not in active_entities(copilot)


@pytest.mark.e2e
def test_group_course_teacher_composes_canonical_relationship(copilot):
    ask(copilot, "Show me DIN24.")
    assert "DBS24" in ask(copilot, "Which courses does it have?").reply
    reply = ask(copilot, "Who teaches Database Systems?").reply

    assert "Matti Virtanen" in reply
    assert ("get_student_group_courses", {"group_id": 240}) in copilot[1].calls
    assert ("get_course_teachers", {"course_id": 25}) in copilot[1].calls
    assert active_entities(copilot)["COURSE"]["canonical_id"] == 25

    explicit = ask(copilot, "Who teaches Database Systems for DIN24?").reply
    assert "Matti Virtanen" in explicit


@pytest.mark.e2e
def test_course_name_ambiguity_without_group_context_still_clarifies(copilot):
    reply = ask(copilot, "Who teaches Database Systems?", user=801, chat=901).reply

    assert "multiple matching courses" in reply
    assert "DBS24" in reply and "DE103" in reply


@pytest.mark.e2e
def test_group_course_teacher_rejects_course_outside_group(copilot):
    reply = ask(copilot, "Who teaches Mathematics for DIN24?").reply

    assert "not associated" in reply
    assert not any(name == "get_course_teachers" for name, _ in copilot[1].calls)


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("status", "included", "grade", "excluded", "outsider"),
    [
        ("passed", "Elina Demo", 4, "Oskari Example", "Anna Korhonen"),
        ("failed", "Oskari Example", 0, "Elina Demo", "John Smith"),
    ],
)
def test_group_scoped_results_filter_status_and_exclude_outside_students(
    copilot, status, included, grade, excluded, outsider
):
    reply = ask(copilot, f"Who {status} Database Systems in DIN24?").reply

    assert included in reply
    assert f"grade {grade}" in reply
    assert excluded not in reply
    assert outsider not in reply
    assert "Sofia Sample" not in reply
    entities = active_entities(copilot)
    assert entities["STUDENT_GROUP"]["canonical_id"] == 240
    assert entities["COURSE"]["canonical_id"] == 25


@pytest.mark.e2e
def test_group_switch_and_failed_or_ambiguous_resolution_context_rules(copilot):
    ask(copilot, "Show me DIN24.")
    assert "Elina Demo" in ask(copilot, "Which students are in it?").reply
    ask(copilot, "Show me BIT24.")
    assert active_entities(copilot)["STUDENT_GROUP"]["canonical_id"] == 241
    switched_students = ask(copilot, "Which students are in it?").reply
    assert "Anna Korhonen" in switched_students
    assert "Elina Demo" not in switched_students

    assert "could not find" in ask(copilot, "Show me XYZ999.").reply
    assert "BIT24" in ask(copilot, "Which courses does it have?").reply
    assert "multiple matching student groups" in ask(copilot, "Show me group Shared cohort.").reply
    assert active_entities(copilot)["STUDENT_GROUP"]["canonical_id"] == 241


@pytest.mark.e2e
def test_roster_enrollment_pass_fail_and_analytics(copilot):
    ask(copilot, "Show DII101.")
    assert "Anna Korhonen" in ask(copilot, "Who is enrolled?").reply
    assert "Anna Korhonen" in ask(copilot, "Who passed?").reply
    assert "John Smith" in ask(copilot, "Who failed?").reply
    assert "50.0%" in ask(copilot, "What is the pass rate?").reply
    enrollment = ask(copilot, "Is Anna Korhonen enrolled in DII101?").reply
    assert "ENROLLED" in enrollment


@pytest.mark.e2e
def test_student_course_result_grade_and_unrelated_context_preservation(copilot):
    ask(copilot, "Show Anna Korhonen.")
    assert "PASSED" in ask(copilot, "Did she pass DII101?").reply
    assert "grade 5" in ask(copilot, "What grade did she get?").reply
    ask(copilot, "What about MAT101?")
    reply = ask(copilot, "What grade did she get?").reply
    assert "MAT101" in reply and "grade 0" in reply
    assert {kind: row["canonical_id"] for kind, row in active_entities(copilot).items()} == {"STUDENT": 7, "COURSE": 101}


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("student", "pronoun", "expected_status", "expected_grade"),
    [
        ("Elina Demo", "she", "PASSED", 5),
        ("Oskari Example", "he", "FAILED", 0),
    ],
)
def test_student_course_yes_no_returns_actual_pass_or_fail_result(
    copilot, student, pronoun, expected_status, expected_grade
):
    ask(copilot, f"Show me {student}.")

    result = ask(copilot, f"Did {pronoun} pass DII101?").reply
    grade = ask(copilot, f"What grade did {pronoun} get?").reply

    assert expected_status in result
    assert f"grade {expected_grade}" in result
    assert expected_status in grade
    assert f"grade {expected_grade}" in grade


@pytest.mark.e2e
def test_student_course_yes_no_reports_none_when_student_has_no_course_result(copilot):
    ask(copilot, "Show me Sofia Sample.")

    assert ask(copilot, "Did she pass DII101?").reply.endswith("Results: none found.")


@pytest.mark.e2e
def test_explicit_student_in_result_question_replaces_stale_student_only(copilot):
    ask(copilot, "Show me Elina Demo.")
    assert "PASSED" in ask(copilot, "Did she pass DII101?").reply

    reply = ask(copilot, "Did Oskari pass DII101?").reply

    assert "Oskari Example" in reply
    assert "FAILED" in reply and "grade 0" in reply
    assert "Elina Demo" not in reply
    entities = active_entities(copilot)
    assert entities["STUDENT"]["canonical_id"] == 41
    assert entities["COURSE"]["canonical_id"] == 24


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Did Unknown Student pass DII101?", "could not find"),
        ("Did Anna pass DII101?", "multiple matching students"),
    ],
)
def test_unresolved_explicit_student_never_falls_back_to_stale_student(
    copilot, message, expected
):
    ask(copilot, "Show me Elina Demo.")

    reply = ask(copilot, message).reply

    assert expected in reply
    assert "Elina Demo: PASSED" not in reply
    assert active_entities(copilot)["STUDENT"]["canonical_id"] == 40


@pytest.mark.e2e
def test_course_level_passed_query_still_filters_to_passed_students(copilot):
    reply = ask(copilot, "Who passed DII101?").reply

    assert "Elina Demo" in reply and "PASSED" in reply
    assert "Oskari Example" not in reply


@pytest.mark.e2e
def test_teacher_discovery_contact_assignments_and_course_teacher(copilot):
    assert "Matti Virtanen" in ask(copilot, "Find Matti Virtanen.").reply
    assert "matti@example.test" in ask(copilot, "What is his email?").reply
    assert "DII101" in ask(copilot, "Which courses does he teach?").reply
    ask(copilot, "Show DII101.")
    assert "Matti Virtanen" in ask(copilot, "Who teaches it?").reply


@pytest.mark.e2e
def test_contextual_specialized_progress_risk_and_study_right_routes(copilot):
    ask(copilot, "Show Anna Korhonen.")
    progress = ask(copilot, "How is she progressing?").reply
    risk = ask(copilot, "Is she at risk?").reply
    study_right = ask(copilot, "What is her study-right status?").reply
    assert "55 ECTS" in progress
    assert "academic risk" in risk
    assert "active study right" in study_right.lower()
    assert ("get_progress", {"student_id": 7}) in copilot[1].calls


@pytest.mark.e2e
def test_explicit_course_and_student_switching(copilot):
    ask(copilot, "Show DII101.")
    assert "John Smith" in ask(copilot, "Who failed MAT101?").reply
    assert "25.0%" in ask(copilot, "What is the pass rate?").reply
    ask(copilot, "Show Anna Korhonen.")
    ask(copilot, "Now show John Smith.")
    assert "John Smith" in ask(copilot, "How is he progressing?").reply


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("message", "label"),
    [("Find Nonexistent Student.", "student"), ("Show course XYZ999.", "course"), ("Find teacher Nobody Person.", "teacher")],
)
def test_unknown_entities_are_controlled_and_not_cached(copilot, message, label):
    response = ask(copilot, message)
    assert f"could not find the requested {label}" in response.reply.lower()
    assert label.upper() not in active_entities(copilot)


@pytest.mark.e2e
def test_ambiguous_entities_request_clarification_without_context(copilot):
    assert "multiple matching students" in ask(copilot, "Find Anna.").reply
    assert "multiple matching teachers" in ask(copilot, "Find teacher Alex.").reply
    assert active_entities(copilot) == {}


@pytest.mark.e2e
@pytest.mark.parametrize(
    "message, expected",
    [("How is she progressing?", "student"), ("Who teaches it?", "course"), ("What is his email?", "teacher")],
)
def test_context_references_in_new_conversation_require_clarification(copilot, message, expected):
    response = ask(copilot, message, user=901, chat=hash(message) % 100000 + 1000)
    assert expected in response.reply.lower()
    assert any(term in response.reply.lower() for term in ("which", "provide"))


@pytest.mark.e2e
def test_failed_resolution_preserves_valid_context_and_sessions_are_isolated(copilot):
    ask(copilot, "Show DII101.", user=1, chat=10)
    assert "could not find" in ask(copilot, "Show XYZ999.", user=1, chat=10).reply
    assert "50.0%" in ask(copilot, "What is the pass rate?", user=1, chat=10).reply
    response = ask(copilot, "Who teaches it?", user=2, chat=20)
    assert "Which course" in response.reply


class ChatServiceBackendAdapter:
    def __init__(self, copilot):
        self.copilot = copilot

    async def send_message(self, **kwargs):
        request = ChatRequest(message=kwargs.pop("message"), **kwargs)
        return (await self.copilot[0].process_message(request, trusted_telegram=True)).reply


class CapturingMessage:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_chat_action(self, action):
        return None

    async def reply_text(self, text):
        self.replies.append(text)


@pytest.mark.e2e
def test_telegram_handler_multi_turn_group_and_student_workflow(copilot, monkeypatch):
    monkeypatch.setattr(handlers, "backend_client", ChatServiceBackendAdapter(copilot))

    async def send(text, user, chat):
        message = CapturingMessage(text)
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=user, username=f"tutor-{user}"),
            effective_chat=SimpleNamespace(id=chat),
        )
        await handlers.handle_message(update, None)
        return message.replies[0]

    assert "DIN24" in asyncio.run(send("Show me DIN24.", 41, 51))
    assert "Elina Demo" in asyncio.run(send("Which students are in it?", 41, 51))
    courses = asyncio.run(send("Which courses does it have?", 41, 51))
    assert "DII101" in courses and "DBS24" in courses and "WEB24" in courses
    assert "Matti Virtanen" in asyncio.run(send("Who teaches Database Systems?", 41, 51))
    assert "Elina Demo" in asyncio.run(send("Show me Elina Demo.", 41, 51))
    result = asyncio.run(send("Did she pass DII101?", 41, 51))
    assert "PASSED" in result and "grade 5" in result
    assert "grade 5" in asyncio.run(send("What grade did she get?", 41, 51))
    assert "Which student group" in asyncio.run(send("Which students are in it?", 42, 52))
