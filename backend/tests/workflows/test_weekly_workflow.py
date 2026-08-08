import asyncio
import logging
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI

from app.services.scheduler import DailyTimeTrigger, Scheduler
from app.workflows.weekly import (
    WEEKLY_WORKFLOW_JOB_ID,
    WeeklyWorkflow,
    register_weekly_workflow,
)


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


class FakeEctsAnalyticsProvider:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else ects_result()
        self.error = error
        self.calls = []

    def calculate_ects_for_cohort(self, student_ids):
        self.calls.append(student_ids)
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


class FakeReportStore:
    def __init__(self, receipt=None, error=None):
        self.receipt = receipt or {"status": "saved", "report_id": 19}
        self.error = error
        self.calls = []

    def save_report(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.receipt


def ects_result(processed=2, failed=0):
    return {
        "success": processed > 0,
        "processed": processed,
        "failed": failed,
        "summary": {
            "behind_count": 1 if processed else 0,
            "on_track_count": max(processed - 1, 0),
            "ahead_count": 0,
            "average_completed_ects": 47.5 if processed else 0.0,
            "average_progress_percentage": 82.0 if processed else 0.0,
        },
    }


def risk_result(status="COMPLETE", risk_level="LOW"):
    return {
        "success": True,
        "assessment_status": status,
        "risk_level": risk_level if status == "COMPLETE" else None,
    }


def workflow(
    *,
    students=None,
    events=None,
    event_error=None,
    ects=None,
    ects_error=None,
    risks=None,
    risk_errors=None,
    directory_error=None,
    store=None,
):
    return WeeklyWorkflow(
        student_directory=FakeStudentDirectory(students, directory_error),
        event_provider=FakeEventProvider(events, event_error),
        ects_analytics_provider=FakeEctsAnalyticsProvider(ects, ects_error),
        risk_provider=FakeRiskProvider(risks, risk_errors),
        report_store=store or FakeReportStore(),
        timezone="Europe/Helsinki",
        student_page_size=1,
    )


def section(result, name):
    return next(item for item in result.sections if item.name == name)


def test_direct_run_uses_previous_completed_week_and_non_identifying_logs(caplog):
    instance = workflow(
        students=[{"id": 2, "name": "Sensitive Student"}, {"id": 1}],
        events={"success": True, "events": [{"id": 3}]},
        risks={1: risk_result(), 2: risk_result()},
    )

    with caplog.at_level(logging.INFO, logger="academic-copilot.workflows.weekly"):
        result = instance.run(
            now=datetime(2026, 1, 5, 0, 30, tzinfo=ZoneInfo("Europe/Helsinki"))
        )

    assert result.execution_key == "weekly:2025-12-29:2026-01-05"
    assert result.period_start == "2025-12-29"
    assert result.period_end == "2026-01-05"
    assert result.started_at == result.completed_at
    assert instance._event_provider.calls == [("2025-12-29", "2026-01-04")]
    assert instance._ects_analytics_provider.calls == [[1, 2]]
    assert instance._risk_provider.calls == [
        (2, datetime(2026, 1, 5).date()),
        (1, datetime(2026, 1, 5).date()),
    ]
    assert result.status == "completed"
    assert result.persistence_status == "saved"
    assert result.report_id == 19
    assert "Sensitive Student" not in caplog.text


def test_empty_successful_sources_are_completed_with_zero_counts():
    result = workflow(students=[], events={"success": True, "events": []}, risks={}).run(
        now=datetime(2026, 1, 6, 12, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.status == "completed"
    assert section(result, "academic_events").count == 0
    assert section(result, "student_directory").count == 0
    assert section(result, "current_progress").count == 0
    assert section(result, "current_academic_risks").count == 0
    assert all(item.status == "completed" for item in result.sections)


def test_partial_risk_assessment_is_not_converted_to_a_risk_level_distribution():
    result = workflow(
        students=[{"id": 1}],
        risks={1: risk_result("PARTIAL")},
    ).run(now=datetime(2026, 2, 2, 6, tzinfo=ZoneInfo("Europe/Helsinki")))

    risks = section(result, "current_academic_risks")
    assert result.status == "partial"
    assert risks.status == "partial"
    assert risks.count == 1
    assert risks.details["partial_assessments"] == 1
    assert risks.details["risk_levels_available"] == 0
    assert risks.reason_codes == ["RISK_LEVELS_UNAVAILABLE_FOR_PARTIAL_ASSESSMENTS"]


def test_unavailable_events_are_never_reported_as_zero():
    result = workflow(
        students=[],
        events={"success": False, "error": "EVENT_SOURCE_UNAVAILABLE"},
        risks={},
    ).run(now=datetime(2026, 2, 2, 6, tzinfo=ZoneInfo("Europe/Helsinki")))

    events = section(result, "academic_events")
    assert result.status == "partial"
    assert events.status == "unavailable"
    assert events.count is None
    assert events.reason_codes == ["EVENT_SOURCE_UNAVAILABLE"]


def test_persistence_failure_is_explicit_and_changes_an_otherwise_complete_result_to_partial():
    result = workflow(
        students=[],
        risks={},
        store=FakeReportStore(error=RuntimeError("database unavailable")),
    ).run(now=datetime(2026, 2, 2, 6, tzinfo=ZoneInfo("Europe/Helsinki")))

    assert result.status == "partial"
    assert result.persistence_status == "failed"
    assert result.report_id is None
    assert result.errors == ["report_persistence:WEEKLY_REPORT_STORE_FAILED"]


def test_existing_execution_key_is_reported_without_creating_a_second_stored_result():
    store = FakeReportStore(receipt={"status": "already_stored", "report_id": 23})
    result = workflow(students=[], risks={}, store=store).run(
        now=datetime(2026, 2, 2, 6, tzinfo=ZoneInfo("Europe/Helsinki"))
    )

    assert result.persistence_status == "already_stored"
    assert result.report_id == 23
    assert len(store.calls) == 1


def test_registers_one_monday_job_in_helsinki_and_ignores_duplicates():
    async def run_test():
        scheduler = Scheduler(timezone="UTC")
        registered = await register_weekly_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )
        duplicate = await register_weekly_workflow(
            scheduler,
            job=lambda: None,
            hour=6,
            minute=15,
            timezone="Europe/Helsinki",
        )

        job = scheduler._jobs[WEEKLY_WORKFLOW_JOB_ID]
        assert registered is True
        assert duplicate is False
        assert isinstance(job.trigger, DailyTimeTrigger)
        assert job.trigger.days_of_week == {0}
        assert (job.trigger.hour, job.trigger.minute) == (6, 15)
        assert job.trigger.tz.key == "Europe/Helsinki"

    asyncio.run(run_test())


def test_fastapi_lifecycle_registers_and_stops_weekly_job():
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
                assert WEEKLY_WORKFLOW_JOB_ID in scheduler._jobs

            assert scheduler.running is False

    asyncio.run(run_test())
