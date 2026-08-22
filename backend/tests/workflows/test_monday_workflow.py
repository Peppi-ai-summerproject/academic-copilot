import asyncio
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI

from app.services.scheduler import DailyTimeTrigger, Scheduler
from app.workflows.monday import (
    AutonomousMondayBriefingRunner,
    MONDAY_WORKFLOW_JOB_ID,
    MondayWorkflow,
    create_database_monday_workflow,
    register_monday_workflow,
)
from app.telegram.notifications import TelegramSendReceipt
from app.workflows.execution_logging import WorkflowExecutionRecorder


@patch("app.workflows.monday.AcademicRiskScoringService")
@patch("app.workflows.monday.TutorMeetingRiskService")
@patch("app.workflows.monday.TutorMeetingRepository")
def test_database_workflow_injects_tutor_meeting_evaluator(
    repository_type, evaluator_type, risk_type
):
    session = Mock()
    repository = repository_type.return_value
    evaluator = evaluator_type.return_value

    create_database_monday_workflow(session=session, timezone="Europe/Helsinki")

    repository_type.assert_called_once_with(session)
    evaluator_type.assert_called_once_with(repository)
    assert risk_type.call_args.args[3] is evaluator


class FakeTutorDirectory:
    def __init__(self, tutors, students_by_tutor):
        self.tutors = tutors
        self.students_by_tutor = students_by_tutor

    def list_active_tutors(self):
        return self.tutors

    def list_students_for_tutor(self, tutor_id):
        return self.students_by_tutor[tutor_id]


class FakeProgressProvider:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def get_progress(self, student_id):
        self.calls.append(student_id)
        return self.results[student_id]


class FakeRiskProvider:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def assess_student_risk(self, student_id, *, as_of_date):
        self.calls.append((student_id, as_of_date))
        return self.results[student_id]


class FakeEventProvider:
    def __init__(self, result=None):
        self.result = result or {"success": True, "events": []}
        self.calls = []

    def get_upcoming_events(self, start_date=None, end_date=None):
        self.calls.append((start_date, end_date))
        return self.result


def progress(student_id, *, remaining=0):
    return {
        "success": True,
        "progress": {
            "student_id": student_id,
            "completed_ects": 60,
            "expected_ects": 60 + remaining,
            "remaining_to_expected_ects": remaining,
            "status": "BEHIND" if remaining else "ON_TRACK",
        },
    }


def risk(student_id, *, points=0):
    return {
        "success": True,
        "student_id": student_id,
        "raw_subtotal": points,
        "indicator_contributions": [{"assigned_points": points}],
        "unavailable_indicators": ["tutor_meetings"],
    }


def workflow(*, tutors, students, progress_results, risk_results, events=None):
    return MondayWorkflow(
        tutor_directory=FakeTutorDirectory(tutors, students),
        progress_provider=FakeProgressProvider(progress_results),
        risk_provider=FakeRiskProvider(risk_results),
        event_provider=FakeEventProvider(events),
        timezone="Europe/Helsinki",
    )


class CapturingTelegramSender:
    def __init__(self):
        self.sent = []

    def send_message(self, *, chat_id, text):
        self.sent.append((chat_id, text))
        return TelegramSendReceipt(provider_message_id=9001)


class CapturingExecutionLogStore:
    def __init__(self):
        self.started = []
        self.finalized = []

    def start_execution(self, record):
        self.started.append(record)

    def finalize_execution(self, record):
        self.finalized.append(record)


def test_direct_run_groups_students_and_builds_unsent_telegram_briefing():
    tutors = [{"id": 1, "display_name": "Tutor One", "telegram_chat_id": 99}]
    students = {
        1: [
            {"id": 20, "name": "Zoe Student", "student_number": "STU-020"},
            {"id": 10, "name": "Ada Student", "student_number": "STU-010"},
        ]
    }
    events = {
        "success": True,
        "events": [{"event_name": "Course deadline", "event_date": "2026-01-02"}],
    }
    result = workflow(
        tutors=tutors,
        students=students,
        progress_results={10: progress(10, remaining=20), 20: progress(20, remaining=5)},
        risk_results={10: risk(10, points=30), 20: risk(20, points=15)},
        events=events,
    ).run(now=datetime(2025, 12, 31, 12, tzinfo=ZoneInfo("UTC")))

    assert result.status == "completed"
    assert result.week_start == "2025-12-29"
    assert result.week_end == "2026-01-04"
    briefing = result.briefings[0]
    assert briefing.summary == {
        "total_students": 2,
        "analysed_students": 2,
        "students_needing_attention": 2,
    }
    assert [student["student_id"] for student in briefing.priority_students] == [10, 20]
    assert briefing.delivery["channel"] == "telegram"
    assert briefing.delivery["delivery_status"] == "NOT_SENT"
    assert "Ada Student" in briefing.delivery["text"]
    assert "Course deadline" in briefing.delivery["text"]


def test_demo_scenario_3_executes_logs_and_delivers_meaningful_weekly_briefing():
    sender = CapturingTelegramSender()
    log_store = CapturingExecutionLogStore()
    monday = workflow(
        tutors=[{"id": 7, "display_name": "DIN24 Tutor", "telegram_chat_id": 7007}],
        students={
            7: [
                {"id": 41, "name": "Oskari Example", "student_number": "DEMO22102"},
                {"id": 43, "name": "Aava Achiever", "student_number": "DEMO25201"},
            ]
        },
        progress_results={
            41: progress(41, remaining=30),
            43: progress(43, remaining=0),
        },
        risk_results={
            41: risk(41, points=30),
            43: risk(43, points=0),
        },
        events={
            "success": True,
            "events": [
                {"event_name": "Course registration deadline", "event_date": "2026-01-07"}
            ],
        },
    )
    runner = AutonomousMondayBriefingRunner(
        workflow=monday,
        sender=sender,
        execution_recorder=WorkflowExecutionRecorder(log_store),
    )

    result = runner.run(
        now=datetime(2026, 1, 5, 8, tzinfo=ZoneInfo("Europe/Helsinki")),
        trigger_type="direct",
    )

    assert result.status == "completed"
    assert result.briefings[0].summary == {
        "total_students": 2,
        "analysed_students": 2,
        "students_needing_attention": 1,
    }
    assert result.briefings[0].delivery["delivery_status"] == "DELIVERED"
    assert result.briefings[0].delivery["provider_message_id"] == 9001
    assert len(sender.sent) == 1
    chat_id, message = sender.sent[0]
    assert chat_id == 7007
    assert "Monday briefing for DIN24 Tutor" in message
    assert "Assigned students: 2" in message
    assert "Students needing attention: 1" in message
    assert "Oskari Example; 30 ECTS below expected" in message
    assert "Aava Achiever" not in message
    assert "Course registration deadline" in message
    assert len(log_store.started) == len(log_store.finalized) == 1
    finalized = log_store.finalized[0]
    assert finalized.workflow_name == "monday_tutor_briefing"
    assert finalized.trigger_type == "direct"
    assert finalized.status == "completed"
    assert (finalized.requested_count, finalized.succeeded_count, finalized.failed_count) == (1, 1, 0)
    assert "Oskari" not in str(finalized)


def test_tutor_without_students_is_safe_and_missing_destination_is_explicit():
    result = workflow(
        tutors=[{"id": 1, "display_name": "Tutor One", "telegram_chat_id": None}],
        students={1: []},
        progress_results={},
        risk_results={},
    ).run(now=datetime(2026, 1, 5, 8, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "partial"
    briefing = result.briefings[0]
    assert briefing.summary["total_students"] == 0
    assert briefing.summary["students_needing_attention"] == 0
    assert briefing.delivery["delivery_status"] == "NO_DESTINATION"
    assert any("destination" in warning.lower() for warning in briefing.warnings)


def test_one_student_analysis_failure_produces_partial_result():
    result = workflow(
        tutors=[{"id": 1, "display_name": "Tutor One", "telegram_chat_id": 9}],
        students={
            1: [
                {"id": 1, "name": "Available Student"},
                {"id": 2, "name": "Unavailable Student"},
            ]
        },
        progress_results={1: progress(1), 2: {"success": False, "error": "UNAVAILABLE"}},
        risk_results={1: risk(1), 2: {"success": False, "error": "UNAVAILABLE"}},
    ).run(now=datetime(2026, 1, 5, 8, tzinfo=ZoneInfo("UTC")))

    assert result.status == "partial"
    assert result.briefings[0].summary["analysed_students"] == 1
    assert any("student 2" in warning.lower() for warning in result.briefings[0].warnings)


def test_all_student_analytics_fail_returns_failed_result():
    result = workflow(
        tutors=[{"id": 1, "display_name": "Tutor One", "telegram_chat_id": 9}],
        students={1: [{"id": 1, "name": "Unavailable Student"}]},
        progress_results={1: {"success": False, "error": "UNAVAILABLE"}},
        risk_results={1: {"success": False, "error": "UNAVAILABLE"}},
    ).run(now=datetime(2026, 1, 5, 8, tzinfo=ZoneInfo("UTC")))

    assert result.status == "failed"
    assert result.errors == ["Academic analysis failed for every assigned student."]


def test_registers_one_explicit_monday_job_and_ignores_duplicates():
    async def run_test():
        scheduler = Scheduler(timezone="Europe/Helsinki")

        registered = await register_monday_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )
        duplicate = await register_monday_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )

        job = scheduler._jobs[MONDAY_WORKFLOW_JOB_ID]
        assert registered is True
        assert duplicate is False
        assert isinstance(job.trigger, DailyTimeTrigger)
        assert job.trigger.days_of_week == {0}
        assert (job.trigger.hour, job.trigger.minute) == (6, 15)
        assert job.trigger.tz.key == "Europe/Helsinki"

    asyncio.run(run_test())


def test_fastapi_lifecycle_registers_and_stops_monday_job():
    pytest.importorskip("langgraph")
    from app.main import lifespan

    async def run_test():
        app = FastAPI()
        with (
            patch("app.main.settings.scheduler_enabled", True),
            patch("app.main.settings.telegram_webhook_enabled", False),
        ):
            async with lifespan(app):
                scheduler = app.state.scheduler
                assert scheduler.running is True
                assert MONDAY_WORKFLOW_JOB_ID in scheduler._jobs

            assert scheduler.running is False

    asyncio.run(run_test())
