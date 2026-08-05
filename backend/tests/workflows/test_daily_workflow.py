import asyncio
import logging
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI

from app.services.scheduler import DailyTimeTrigger, Scheduler
from app.workflows.daily import (
    DAILY_WORKFLOW_JOB_ID,
    DailyWorkflow,
    register_daily_workflow,
)


class FakeAutomaticRiskDetection:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def run(self, *, evaluation_time=None):
        self.calls.append(evaluation_time)
        if self.error:
            raise self.error
        return self.result


class FakeStudentDirectory:
    def __init__(self, students=None, error=None):
        self.students = students or []
        self.error = error
        self.calls = []

    def search_students(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        offset = kwargs["offset"]
        limit = kwargs["limit"]
        return self.students[offset : offset + limit], len(self.students)


class FakeEventProvider:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else {"success": True, "events": []}
        self.error = error
        self.calls = []

    def get_upcoming_events(self, start_date=None, end_date=None):
        self.calls.append((start_date, end_date))
        if self.error:
            raise self.error
        return self.result


class FakeRiskProvider:
    def __init__(self, results=None, errors=None):
        self.results = results or {}
        self.errors = errors or {}
        self.calls = []

    def assess_student_risk(self, student_id, *, as_of_date):
        self.calls.append((student_id, as_of_date))
        if student_id in self.errors:
            raise self.errors[student_id]
        return self.results[student_id]


def risk_result(status="COMPLETE"):
    return {
        "success": True,
        "assessment_status": status,
        "raw_subtotal": 0,
        "risk_level": "LOW" if status == "COMPLETE" else None,
    }


def workflow(*, students=None, events=None, event_error=None, risks=None, risk_errors=None, directory_error=None):
    return DailyWorkflow(
        student_directory=FakeStudentDirectory(students, directory_error),
        event_provider=FakeEventProvider(events, event_error),
        risk_provider=FakeRiskProvider(risks, risk_errors),
        timezone="Europe/Helsinki",
        student_page_size=1,
    )


def test_direct_run_uses_helsinki_calendar_day_and_aggregate_only_logs(caplog):
    instance = workflow(
        students=[{"id": 1, "name": "Sensitive Student"}, {"id": 2}],
        events={"success": True, "events": [{"id": 7}, {"id": 8}]},
        risks={1: risk_result(), 2: risk_result()},
    )

    with caplog.at_level(logging.INFO, logger="academic-copilot.workflows.daily"):
        result = instance.run(now=datetime(2025, 12, 31, 23, 30, tzinfo=ZoneInfo("UTC")))

    assert result.execution_date == "2026-01-01"
    assert result.execution_key == "daily:2026-01-01"
    assert result.status == "partial"
    assert result.academic_events.status == "completed"
    assert result.academic_events.count == 2
    assert result.student_risks.status == "completed"
    assert result.student_risks.count == 2
    assert result.pending_tutor_actions.status == "unavailable"
    assert result.pending_tutor_actions.count is None
    assert instance._event_provider.calls == [("2026-01-01", "2026-01-01")]
    assert "Sensitive Student" not in caplog.text


def test_successful_zero_item_checks_are_not_unavailable():
    result = workflow(students=[], events={"success": True, "events": []}, risks={}).run(
        now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.status == "partial"
    assert result.academic_events.status == "completed"
    assert result.academic_events.count == 0
    assert result.student_risks.status == "completed"
    assert result.student_risks.count == 0
    assert result.pending_tutor_actions.status == "unavailable"
    assert result.pending_tutor_actions.count is None


def test_unavailable_event_data_is_never_reported_as_zero():
    result = workflow(
        students=[],
        events={"success": False, "error": "EVENT_SOURCE_UNAVAILABLE"},
        risks={},
    ).run(now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "partial"
    assert result.academic_events.status == "unavailable"
    assert result.academic_events.count is None
    assert result.academic_events.reason_codes == ["EVENT_SOURCE_UNAVAILABLE"]


def test_partial_risk_assessment_is_aggregated_without_student_payloads():
    result = workflow(
        students=[{"id": 1}, {"id": 2}],
        risks={
            1: risk_result("PARTIAL"),
            2: {"success": False, "error": "STUDY_RIGHT_UNAVAILABLE"},
        },
    ).run(now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "partial"
    assert result.student_risks.status == "partial"
    assert result.student_risks.count == 1
    assert result.student_risks.details == {
        "students_discovered": 2,
        "students_assessed": 1,
        "partial_assessments": 1,
        "unavailable_assessments": 1,
        "failed_assessments": 0,
    }
    assert result.student_risks.reason_codes == ["STUDY_RIGHT_UNAVAILABLE"]


def test_all_unavailable_checks_produce_unavailable_workflow_status():
    result = workflow(
        students=[{"id": 1}],
        events={"success": False, "error": "EVENT_SOURCE_UNAVAILABLE"},
        risks={1: {"success": False, "error": "RISK_SOURCE_UNAVAILABLE"}},
    ).run(now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "unavailable"
    assert result.student_risks.status == "unavailable"
    assert result.student_risks.count is None


def test_total_independent_check_failure_produces_failed_result():
    result = workflow(
        event_error=RuntimeError("event check failed"),
        directory_error=RuntimeError("student directory failed"),
    ).run(now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "failed"
    assert result.academic_events.status == "failed"
    assert result.student_risks.status == "failed"
    assert result.errors == [
        "academic_events:ACADEMIC_EVENTS_CHECK_FAILED",
        "student_risks:STUDENT_DIRECTORY_CHECK_FAILED",
    ]


def test_daily_workflow_uses_issue_104_automatic_detection_when_configured():
    detection = FakeAutomaticRiskDetection(
        type(
            "DetectionResult",
            (),
            {
                "status": "partial",
                "active_student_count": 3,
                "evaluated_student_count": 3,
                "at_risk_student_count": 2,
                "risk_level_counts": {
                    "LOW": 1,
                    "MEDIUM": 1,
                    "HIGH": 1,
                    "CRITICAL": 0,
                },
                "errors": [],
            },
        )()
    )
    instance = DailyWorkflow(
        event_provider=FakeEventProvider(),
        timezone="Europe/Helsinki",
        automatic_risk_detection=detection,
    )

    result = instance.run(
        now=datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert detection.calls == [datetime(2026, 1, 1, 7, tzinfo=ZoneInfo("Europe/Helsinki"))]
    assert result.student_risks.status == "partial"
    assert result.student_risks.count == 3
    assert result.student_risks.details == {
        "active_students_discovered": 3,
        "students_assessed": 3,
        "students_requiring_tutor_attention": 2,
        "low_risk_students": 1,
        "medium_risk_students": 1,
        "high_risk_students": 1,
        "critical_risk_students": 0,
    }


def test_registers_one_explicit_daily_job_and_ignores_duplicates():
    async def run_test():
        scheduler = Scheduler(timezone="UTC")

        registered = await register_daily_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )
        duplicate = await register_daily_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )

        job = scheduler._jobs[DAILY_WORKFLOW_JOB_ID]
        assert registered is True
        assert duplicate is False
        assert isinstance(job.trigger, DailyTimeTrigger)
        assert job.trigger.days_of_week is None
        assert (job.trigger.hour, job.trigger.minute) == (6, 15)
        assert job.trigger.tz.key == "Europe/Helsinki"

    asyncio.run(run_test())


def test_fastapi_lifecycle_registers_and_stops_daily_job():
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
                assert DAILY_WORKFLOW_JOB_ID in scheduler._jobs

            assert scheduler.running is False

    asyncio.run(run_test())
