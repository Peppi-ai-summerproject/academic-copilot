"""Issue #98 contract tests for aggregate weekly academic analytics."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.workflows.weekly import _ReportScopedEventProvider, WeeklyWorkflow


class FakeStudentDirectory:
    def __init__(self, students: list[dict] | None = None, error: Exception | None = None):
        self.students = students or []
        self.error = error

    def search_students(self, *, limit: int, offset: int, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.students[offset : offset + limit], len(self.students)


class FakeEventProvider:
    def get_upcoming_events(self, **_kwargs):
        return {"success": True, "events": []}


class FakeEctsAnalyticsProvider:
    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result or {
            "success": True,
            "processed": 0,
            "failed": 0,
            "summary": {
                "behind_count": 0,
                "on_track_count": 0,
                "ahead_count": 0,
                "average_completed_ects": 0.0,
                "average_progress_percentage": 0.0,
            },
        }
        self.error = error
        self.calls: list[list[int]] = []

    def calculate_ects_for_cohort(self, student_ids: list[int]):
        self.calls.append(student_ids)
        if self.error is not None:
            raise self.error
        return self.result


class FakeRiskProvider:
    def __init__(self, results: dict[int, dict] | None = None, errors: set[int] | None = None):
        self.results = results or {}
        self.errors = errors or set()
        self.calls: list[tuple[int, object]] = []

    def assess_student_risk(self, student_id: int, *, as_of_date):
        self.calls.append((student_id, as_of_date))
        if student_id in self.errors:
            raise RuntimeError("risk provider unavailable")
        return self.results[student_id]


class FakeReportStore:
    def __init__(self):
        self.payloads: list[dict] = []

    def save_report(self, **kwargs):
        self.payloads.append(kwargs["report_payload"])
        return {"status": "saved", "report_id": 98}


def canonical_risk(level: str) -> dict:
    return {
        "success": True,
        "assessment_status": "COMPLETE",
        "risk_level": level,
    }


def partial_risk(risk_level: str | None = None) -> dict:
    return {
        "success": True,
        "assessment_status": "PARTIAL",
        "risk_level": risk_level,
    }


def create_workflow(
    *,
    students: list[dict],
    progress: dict | None = None,
    progress_error: Exception | None = None,
    risks: dict[int, dict] | None = None,
    risk_errors: set[int] | None = None,
):
    progress_provider = FakeEctsAnalyticsProvider(progress, progress_error)
    risk_provider = FakeRiskProvider(risks, risk_errors)
    store = FakeReportStore()
    return (
        WeeklyWorkflow(
            student_directory=FakeStudentDirectory(students),
            event_provider=FakeEventProvider(),
            ects_analytics_provider=progress_provider,
            risk_provider=risk_provider,
            report_store=store,
            timezone="Europe/Helsinki",
            student_page_size=100,
        ),
        progress_provider,
        risk_provider,
        store,
    )


def run(instance: WeeklyWorkflow):
    return instance.run(
        now=datetime(2026, 2, 2, 6, 0, tzinfo=ZoneInfo("Europe/Helsinki"))
    )


def test_weekly_analytics_aggregates_mixed_canonical_risk_and_progress_once():
    students = [{"id": student_id} for student_id in range(1, 7)]
    instance, progress_provider, risk_provider, store = create_workflow(
        students=students,
        progress={
            "success": True,
            "processed": 5,
            "failed": 1,
            "summary": {
                "behind_count": 2,
                "on_track_count": 2,
                "ahead_count": 1,
                "average_completed_ects": 72.5,
                "average_progress_percentage": 80.0,
            },
        },
        risks={
            1: canonical_risk("LOW"),
            2: canonical_risk("MEDIUM"),
            3: canonical_risk("HIGH"),
            4: canonical_risk("CRITICAL"),
            # A normalized partial level is still incomplete evidence and must
            # remain in the PARTIAL bucket rather than inflate HIGH.
            5: partial_risk("HIGH"),
            6: {"success": False, "error": "RISK_SOURCE_UNAVAILABLE"},
        },
    )

    result = run(instance)
    analytics = result.analytics

    assert result.period_start == "2026-01-26"
    assert result.period_end == "2026-02-02"
    assert analytics["report_period"] == {
        "start_date": "2026-01-26",
        "end_date": "2026-02-02",
        "end_exclusive": True,
        "timezone": "Europe/Helsinki",
    }
    assert analytics["population"] == {"status": "completed", "student_count": 6}
    assert analytics["progress_statistics"] == {
        "status": "partial",
        "students_processed": 5,
        "students_unavailable": 1,
        "behind_count": 2,
        "on_track_count": 2,
        "ahead_count": 1,
        "average_completed_ects": 72.5,
        "average_progress_percentage": 80.0,
    }
    assert analytics["risk_summary"] == {
        "status": "partial",
        "student_population_count": 6,
        "students_assessed": 5,
        "LOW": 1,
        "MEDIUM": 1,
        "HIGH": 1,
        "CRITICAL": 1,
        "PARTIAL": 1,
        "UNAVAILABLE": 1,
        "requires_tutor_attention": 3,
    }
    assert sum(
        analytics["risk_summary"][bucket]
        for bucket in ("LOW", "MEDIUM", "HIGH", "CRITICAL", "PARTIAL", "UNAVAILABLE")
    ) == analytics["population"]["student_count"]
    assert analytics["important_findings"] == {
        "kind": "CURRENT_WEEKLY_INDICATORS",
        "historical_comparison_available": False,
        "progress_distribution": {"BEHIND": 2, "ON_TRACK": 2, "AHEAD": 1},
        "risk_distribution": {
            "LOW": 1,
            "MEDIUM": 1,
            "HIGH": 1,
            "CRITICAL": 1,
            "PARTIAL": 1,
            "UNAVAILABLE": 1,
        },
    }
    assert progress_provider.calls == [[1, 2, 3, 4, 5, 6]]
    assert risk_provider.calls == [(student_id, result.period_end and datetime(2026, 2, 2).date()) for student_id in range(1, 7)]
    assert store.payloads[0]["analytics"] == analytics
    json.dumps(result.to_dict())


def test_partial_or_failed_progress_is_visible_and_never_coerced_to_zero():
    instance, _progress_provider, _risk_provider, _store = create_workflow(
        students=[{"id": 1}],
        progress_error=RuntimeError("progress source unavailable"),
        risks={1: canonical_risk("LOW")},
    )

    analytics = run(instance).analytics

    assert analytics["progress_statistics"] == {
        "status": "failed",
        "students_processed": None,
        "students_unavailable": None,
        "behind_count": None,
        "on_track_count": None,
        "ahead_count": None,
        "average_completed_ects": None,
        "average_progress_percentage": None,
    }
    assert analytics["data_quality"]["section_statuses"]["current_progress"] == "failed"


def test_empty_population_has_a_complete_zero_analytics_report():
    instance, progress_provider, risk_provider, _store = create_workflow(
        students=[], risks={}
    )

    analytics = run(instance).analytics

    assert analytics["population"]["student_count"] == 0
    assert analytics["progress_statistics"]["students_processed"] == 0
    assert analytics["risk_summary"] == {
        "status": "completed",
        "student_population_count": 0,
        "students_assessed": 0,
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 0,
        "CRITICAL": 0,
        "PARTIAL": 0,
        "UNAVAILABLE": 0,
        "requires_tutor_attention": 0,
    }
    assert progress_provider.calls == []
    assert risk_provider.calls == []


def test_individual_risk_failure_is_an_unavailable_bucket_with_quality_detail():
    instance, _progress_provider, _risk_provider, _store = create_workflow(
        students=[{"id": 1}, {"id": 2}],
        progress={
            "success": True,
            "processed": 2,
            "failed": 0,
            "summary": {
                "behind_count": 0,
                "on_track_count": 2,
                "ahead_count": 0,
                "average_completed_ects": 60.0,
                "average_progress_percentage": 100.0,
            },
        },
        risks={1: canonical_risk("LOW")},
        risk_errors={2},
    )

    analytics = run(instance).analytics

    assert analytics["risk_summary"]["LOW"] == 1
    assert analytics["risk_summary"]["UNAVAILABLE"] == 1
    assert analytics["data_quality"]["risk_failed_assessments"] == 1
    assert analytics["data_quality"]["risk_explicitly_unavailable_assessments"] == 0


def test_report_scoped_event_provider_reuses_one_identical_canonical_risk_query():
    class CountingEventProvider:
        def __init__(self):
            self.calls: list[tuple[str | None, str | None]] = []

        def get_upcoming_events(self, start_date=None, end_date=None):
            self.calls.append((start_date, end_date))
            return {"success": True, "events": []}

    source = CountingEventProvider()
    provider = _ReportScopedEventProvider(source)

    assert provider.get_upcoming_events("2026-02-02") == {
        "success": True,
        "events": [],
    }
    assert provider.get_upcoming_events("2026-02-02") == {
        "success": True,
        "events": [],
    }
    assert source.calls == [("2026-02-02", None)]
