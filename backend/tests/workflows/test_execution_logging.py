from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.workflows.execution_logging import (
    WorkflowExecutionLog,
    WorkflowExecutionRecorder,
    workflow_outcome,
)
from app.workflows.academic_alerts import (
    AcademicAlertGenerationResult,
    AcademicAlertWorkflow,
)
from app.workflows.automatic_risk_detection import (
    AutomaticRiskDetectionWorkflow,
)
from app.workflows.weekly_tutor_briefing import (
    TutorBriefingAudience,
    WeeklyTutorBriefingGenerator,
    WeeklyTutorBriefingInput,
)
from app.telegram.notifications import AcademicAlertNotificationDelivery


class FakeExecutionLogStore:
    def __init__(self, *, fail_start: bool = False, fail_finalize: bool = False) -> None:
        self.fail_start = fail_start
        self.fail_finalize = fail_finalize
        self.started: list[WorkflowExecutionLog] = []
        self.finalized: list[WorkflowExecutionLog] = []

    def start_execution(self, record: WorkflowExecutionLog) -> None:
        if self.fail_start:
            raise RuntimeError("database unavailable")
        self.started.append(record)

    def finalize_execution(self, record: WorkflowExecutionLog) -> None:
        if self.fail_finalize:
            raise RuntimeError("database unavailable")
        self.finalized.append(record)


def controlled_clock(*values: datetime):
    remaining = iter(values)
    return lambda: next(remaining)


def controlled_monotonic(*values: int):
    remaining = iter(values)
    return lambda: next(remaining)


def test_recorder_stores_utc_start_final_status_and_nonnegative_duration():
    store = FakeExecutionLogStore()
    recorder = WorkflowExecutionRecorder(
        store,
        now=controlled_clock(
            datetime(2026, 8, 8, 6, 0, tzinfo=timezone(timedelta(hours=3))),
            datetime(2026, 8, 8, 3, 0, 2, tzinfo=timezone.utc),
        ),
        monotonic_ns=controlled_monotonic(100_000_000, 2_850_000_000),
    )

    result = recorder.run(
        workflow_name="academic_daily_workflow",
        execution_key="daily:2026-08-08",
        trigger_type="scheduler",
        operation=lambda: "result",
        outcome_for=lambda _: workflow_outcome(
            status="completed",
            requested_count=5,
            processed_count=5,
            succeeded_count=4,
            failed_count=0,
            skipped_count=0,
            warnings=["safe warning"],
            errors=["event:EVENT_SOURCE_UNAVAILABLE"],
        ),
    )

    assert result == "result"
    assert len(store.started) == 1
    assert len(store.finalized) == 1
    started = store.started[0]
    finalized = store.finalized[0]
    assert started.status == "running"
    assert started.started_at == datetime(2026, 8, 8, 3, 0, tzinfo=timezone.utc)
    assert finalized.execution_id == started.execution_id
    assert finalized.correlation_id == started.execution_id
    assert finalized.trigger_type == "scheduler"
    assert finalized.status == "completed"
    assert finalized.duration_ms == 2750
    assert finalized.warning_count == 1
    assert finalized.error_count == 1
    assert finalized.safe_error_code == "EVENT_SOURCE_UNAVAILABLE"
    assert finalized.safe_error_summary == "Workflow reported one or more safe error codes."


def test_nested_executions_share_correlation_and_reference_parent():
    store = FakeExecutionLogStore()
    recorder = WorkflowExecutionRecorder(
        store,
        now=controlled_clock(*([datetime(2026, 8, 8, tzinfo=timezone.utc)] * 4)),
        monotonic_ns=controlled_monotonic(0, 1, 2, 3),
    )

    recorder.run(
        workflow_name="academic_daily_workflow",
        execution_key="daily:2026-08-08",
        trigger_type="direct",
        operation=lambda: recorder.run(
            workflow_name="automatic_risk_detection",
            execution_key="risk-detection:2026-08-08",
            trigger_type="direct",
            operation=lambda: "nested",
            outcome_for=lambda _: workflow_outcome(status="completed"),
        ),
        outcome_for=lambda _: workflow_outcome(status="completed"),
    )

    parent, child = store.started
    assert parent.trigger_type == "direct"
    assert child.trigger_type == "workflow"
    assert child.correlation_id == parent.execution_id
    assert child.parent_execution_id == parent.execution_id


def test_start_persistence_failure_does_not_change_successful_workflow_result(caplog):
    store = FakeExecutionLogStore(fail_start=True)
    recorder = WorkflowExecutionRecorder(
        store,
        now=controlled_clock(*([datetime(2026, 8, 8, tzinfo=timezone.utc)] * 2)),
        monotonic_ns=controlled_monotonic(0, 0),
    )

    with caplog.at_level("WARNING"):
        result = recorder.run(
            workflow_name="academic_alert_generation",
            execution_key=None,
            trigger_type="direct",
            operation=lambda: {"business": "unchanged"},
            outcome_for=lambda _: workflow_outcome(status="completed"),
        )

    assert result == {"business": "unchanged"}
    assert len(store.finalized) == 1
    assert "database unavailable" not in caplog.text
    assert "Workflow history start persistence failed" in caplog.text


def test_original_exception_is_preserved_and_raw_message_is_not_persisted():
    store = FakeExecutionLogStore()
    recorder = WorkflowExecutionRecorder(
        store,
        now=controlled_clock(*([datetime(2026, 8, 8, tzinfo=timezone.utc)] * 2)),
        monotonic_ns=controlled_monotonic(0, 0),
    )

    with pytest.raises(ValueError, match="private student detail"):
        recorder.run(
            workflow_name="weekly_tutor_briefing",
            execution_key=None,
            trigger_type="direct",
            operation=lambda: (_ for _ in ()).throw(ValueError("private student detail")),
            outcome_for=lambda _: workflow_outcome(status="completed"),
        )

    final = store.finalized[0]
    assert final.status == "failed"
    assert final.safe_error_code == "WORKFLOW_EXECUTION_FAILED"
    assert final.safe_error_summary == "Workflow raised before producing a result."
    assert "private student detail" not in str(final)


def test_unsafe_error_text_is_not_promoted_to_a_durable_error_code():
    outcome = workflow_outcome(
        status="partial",
        errors=["student@example.test / sensitive detail"],
    )

    assert outcome.error_count == 1
    assert outcome.safe_error_code is None
    assert outcome.safe_error_summary == "Workflow reported one or more errors."


def test_instrumented_direct_workflows_record_aggregate_outcomes_only():
    class EmptyDirectory:
        def list_active_student_ids(self, student_ids=None):
            return []

    class UnusedRiskProvider:
        def assess_student_risk(self, *args, **kwargs):
            raise AssertionError("empty directory must not call the risk provider")

    class UnusedDelayProvider:
        def detect_student_delay(self, student_id):
            raise AssertionError("empty directory must not call the delay provider")

    class UnusedStudyRightProvider:
        def detect_study_right_risk(self, student_id, *, as_of_date=None):
            raise AssertionError("empty directory must not call the study-right provider")

    class UnusedRecipientResolver:
        def list_active_tutor_recipients_for_student(self, student_id):
            raise AssertionError("empty alert batch must not resolve recipients")

    class UnusedSender:
        def send_message(self, *, chat_id, text):
            raise AssertionError("empty alert batch must not send Telegram")

    at = datetime(2026, 8, 8, tzinfo=timezone.utc)
    risk_store = FakeExecutionLogStore()
    risk_result = AutomaticRiskDetectionWorkflow(
        active_student_directory=EmptyDirectory(),
        risk_provider=UnusedRiskProvider(),
        timezone="UTC",
        execution_recorder=WorkflowExecutionRecorder(
            risk_store,
            now=controlled_clock(at, at),
            monotonic_ns=controlled_monotonic(0, 0),
        ),
    ).run(evaluation_time=at)

    alert_store = FakeExecutionLogStore()
    alert_result = AcademicAlertWorkflow(
        active_student_directory=EmptyDirectory(),
        delay_provider=UnusedDelayProvider(),
        study_right_provider=UnusedStudyRightProvider(),
        timezone="UTC",
        execution_recorder=WorkflowExecutionRecorder(
            alert_store,
            now=controlled_clock(at, at),
            monotonic_ns=controlled_monotonic(0, 0),
        ),
    ).run(evaluation_time=at, risk_detection_result=risk_result)

    briefing_store = FakeExecutionLogStore()
    briefing_result = WeeklyTutorBriefingGenerator(
        execution_recorder=WorkflowExecutionRecorder(
            briefing_store,
            now=controlled_clock(at, at),
            monotonic_ns=controlled_monotonic(0, 0),
        )
    ).generate(
        WeeklyTutorBriefingInput(
            audience=TutorBriefingAudience(tutor_id=1, display_name="Private Tutor"),
            period_start=date(2026, 8, 3),
            period_end=date(2026, 8, 8),
            assigned_student_count=0,
            risk_evaluation_status="completed",
        )
    )

    delivery_store = FakeExecutionLogStore()
    delivery_result = AcademicAlertNotificationDelivery(
        recipient_resolver=UnusedRecipientResolver(),
        sender=UnusedSender(),
        execution_recorder=WorkflowExecutionRecorder(
            delivery_store,
            now=controlled_clock(at, at),
            monotonic_ns=controlled_monotonic(0, 0),
        ),
    ).deliver(alert_result)

    assert risk_result.status == "completed"
    assert alert_result.status == "completed"
    assert briefing_result.status == "completed"
    assert delivery_result.status == "completed"
    assert [record.workflow_name for record in (
        risk_store.finalized[0],
        alert_store.finalized[0],
        briefing_store.finalized[0],
        delivery_store.finalized[0],
    )] == [
        "automatic_risk_detection",
        "academic_alert_generation",
        "weekly_tutor_briefing",
        "academic_alert_notification_delivery",
    ]
    assert "Private Tutor" not in str(briefing_store.finalized[0])
