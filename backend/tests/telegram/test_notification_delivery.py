from __future__ import annotations

from dataclasses import dataclass
import asyncio
import threading

import pytest

from app.telegram.notifications import (
    AcademicAlertNotificationDelivery,
    TelegramApplicationSender,
    TelegramSendReceipt,
    TutorNotificationRecipient,
    render_academic_alert,
    split_telegram_text,
)
from app.workflows.academic_alerts import (
    ALERT_TYPE_ACADEMIC_RISK_DETECTED,
    ALERT_TYPE_DELAYED_PROGRESS,
    AcademicAlert,
    AcademicAlertGenerationResult,
)


class FakeRecipientResolver:
    def __init__(self, rows_by_student: dict[int, list[dict]]):
        self.rows_by_student = rows_by_student
        self.calls: list[int] = []

    def list_active_tutor_recipients_for_student(self, student_id: int) -> list[dict]:
        self.calls.append(student_id)
        return self.rows_by_student.get(student_id, [])


@dataclass
class FakeSender:
    failure: Exception | None = None

    def __post_init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    def send_message(self, *, chat_id: int, text: str) -> TelegramSendReceipt:
        self.sent.append((chat_id, text))
        if self.failure is not None:
            raise self.failure
        return TelegramSendReceipt(provider_message_id=len(self.sent))


def recipient(tutor_id: int, *, chat_id: int | None = None) -> dict:
    return {
        "tutor_id": tutor_id,
        "telegram_user_id": tutor_id + 100,
        "telegram_chat_id": chat_id if chat_id is not None else tutor_id + 200,
        "student_display_name": "Ada_*\nStudent",
    }


def result(*alerts: AcademicAlert, status: str = "completed") -> AcademicAlertGenerationResult:
    return AcademicAlertGenerationResult(
        workflow_name="academic_alert_generation",
        generated_at="2026-08-08T06:00:00+03:00",
        evaluation_date="2026-08-08",
        status=status,  # type: ignore[arg-type]
        students_considered=2,
        alert_count=len(alerts),
        alert_type_counts={},
        source_statuses={
            "delayed_progress": "completed",
            "study_right": "completed",
            "overall_risk": "completed",
        },
        alerts=list(alerts),
    )


def delay_alert(student_id: int) -> AcademicAlert:
    return AcademicAlert(
        alert_type=ALERT_TYPE_DELAYED_PROGRESS,
        affected_student_id=student_id,
        source="delayed_progress",
        severity=None,
        evidence={"delay_ects": 12, "completed_ects": 48, "expected_ects": 60},
    )


def risk_alert(student_id: int) -> AcademicAlert:
    return AcademicAlert(
        alert_type=ALERT_TYPE_ACADEMIC_RISK_DETECTED,
        affected_student_id=student_id,
        source="overall_risk",
        severity="HIGH",
        evidence={
            "assessment_status": "PARTIAL",
            "contributing_indicators": ["academic_delay", "study_right"],
            "unavailable_indicators": ["tutor_meetings"],
        },
    )


@pytest.mark.parametrize(
    ("alert_type", "expected_condition"),
    [
        ("STUDY_RIGHT_EXPIRED", "Study right expired"),
        ("STUDY_RIGHT_EXPIRING_SOON", "Study right expiring soon"),
        ("STUDY_RIGHT_EXTENDED", "Study right extended"),
    ],
)
def test_study_right_templates_render_established_alert_facts(
    alert_type: str,
    expected_condition: str,
):
    alert = AcademicAlert(
        alert_type=alert_type,
        affected_student_id=1,
        source="study_right",
        severity=None,
        evidence={
            "risk_status": "EXPIRING",
            "expiration_date": "2026-08-31",
            "days_until_expiration": 23,
            "extension_count": 2,
        },
    )
    recipient_value = TutorNotificationRecipient(
        tutor_id=1,
        telegram_user_id=101,
        telegram_chat_id=201,
        student_display_name="Ada Student",
    )

    rendered = "".join(render_academic_alert(alert, recipient=recipient_value))

    assert expected_condition in rendered
    assert "Study-right date: 2026-08-31" in rendered
    if alert_type == "STUDY_RIGHT_EXTENDED":
        assert "Recorded extensions: 2" in rendered


def test_delivery_uses_only_resolved_tutors_and_preserves_deterministic_order():
    resolver = FakeRecipientResolver(
        {
            1: [recipient(9, chat_id=909), recipient(3, chat_id=303)],
            2: [recipient(4, chat_id=404)],
        }
    )
    sender = FakeSender()
    delivery = AcademicAlertNotificationDelivery(
        recipient_resolver=resolver,
        sender=sender,
    )

    batch = delivery.deliver(result(delay_alert(2), risk_alert(1)))

    assert resolver.calls == [1, 2]
    assert [chat_id for chat_id, _ in sender.sent] == [303, 909, 404]
    assert batch.status == "completed"
    assert batch.attempted_count == 3
    assert batch.delivered_count == 3
    assert batch.failed_count == 0
    assert batch.skipped_count == 0
    assert "Ada_* Student" in sender.sent[0][1]
    assert "Contributing indicators: academic delay, study right" in sender.sent[0][1]
    assert "Unavailable indicators: tutor meetings" in sender.sent[0][1]
    assert "303" not in str(batch.to_summary())
    assert "Ada" not in str(batch.to_summary())


def test_missing_administrator_provisioned_mapping_is_skipped_without_fallback():
    resolver = FakeRecipientResolver(
        {
            1: [
                {
                    "tutor_id": 1,
                    "telegram_user_id": None,
                    "telegram_chat_id": 123,
                    "student_display_name": "Ada Student",
                }
            ]
        }
    )
    sender = FakeSender()

    batch = AcademicAlertNotificationDelivery(
        recipient_resolver=resolver,
        sender=sender,
    ).deliver(result(delay_alert(1)))

    assert sender.sent == []
    assert batch.status == "partial"
    assert batch.skipped_count == 1
    assert batch.errors == ["NO_AUTHORIZED_TUTOR_RECIPIENT"]


def test_provider_acknowledgement_is_the_only_delivery_success_condition():
    resolver = FakeRecipientResolver({1: [recipient(1)]})

    batch = AcademicAlertNotificationDelivery(
        recipient_resolver=resolver,
        sender=FakeSender(),
    ).deliver(result(delay_alert(1)))

    assert batch.results[0].status == "delivered"
    assert batch.results[0].provider_message_ids == [1]


def test_blocked_recipient_is_a_safe_failed_delivery_without_retry():
    class Forbidden(Exception):
        pass

    sender = FakeSender(failure=Forbidden("not logged"))
    batch = AcademicAlertNotificationDelivery(
        recipient_resolver=FakeRecipientResolver({1: [recipient(1)]}),
        sender=sender,
    ).deliver(result(delay_alert(1)))

    assert len(sender.sent) == 1
    assert batch.status == "failed"
    assert batch.failed_count == 1
    assert batch.errors == ["TELEGRAM_RECIPIENT_BLOCKED"]


def test_partial_source_stays_partial_and_empty_input_is_not_sent():
    sender = FakeSender()
    batch = AcademicAlertNotificationDelivery(
        recipient_resolver=FakeRecipientResolver({}),
        sender=sender,
    ).deliver(result(status="partial"))

    assert sender.sent == []
    assert batch.status == "partial"
    assert batch.attempted_count == 0


def test_failed_alert_source_is_not_presented_as_an_empty_success():
    batch = AcademicAlertNotificationDelivery(
        recipient_resolver=FakeRecipientResolver({}),
        sender=FakeSender(),
    ).deliver(result(status="failed"))

    assert batch.status == "failed"
    assert batch.errors == ["ACADEMIC_ALERT_SOURCE_FAILED"]


def test_chunking_preserves_all_plain_text_in_order_without_truncation():
    source = "A" * 80

    chunks = split_telegram_text(source, maximum_length=24)

    assert len(chunks) > 1
    assert all(len(chunk) <= 24 for chunk in chunks)
    assert "".join(chunk.split(" ", 1)[1] for chunk in chunks) == source


def test_application_sender_uses_the_existing_application_loop_without_network():
    class FakeBot:
        def __init__(self) -> None:
            self.calls: list[tuple[int, str]] = []

        async def send_message(self, *, chat_id: int, text: str):
            self.calls.append((chat_id, text))
            return type("Message", (), {"message_id": 77})()

    class FakeApplication:
        def __init__(self) -> None:
            self.bot = FakeBot()

    loop = asyncio.new_event_loop()
    worker = threading.Thread(target=loop.run_forever)
    worker.start()
    application = FakeApplication()
    try:
        receipt = TelegramApplicationSender(
            application=application,  # type: ignore[arg-type]
            application_loop=loop,
        ).send_message(chat_id=12, text="safe text")
    finally:
        loop.call_soon_threadsafe(loop.stop)
        worker.join(timeout=2)
        loop.close()

    assert receipt.provider_message_id == 77
    assert application.bot.calls == [(12, "safe text")]
