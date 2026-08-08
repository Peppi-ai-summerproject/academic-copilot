"""Deterministic, delivery-only Telegram notifications for Issue #107.

This module consumes already-generated Issue #106 alerts.  It neither
recalculates academic facts nor creates alerts, Tutor assignments, scheduler
jobs, registrations, preferences, retries, or persistent delivery records.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from telegram.ext import Application

from app.repositories.tutor_repository import TutorRepository
from app.workflows.academic_alerts import (
    ALERT_TYPE_ACADEMIC_RISK_DETECTED,
    ALERT_TYPE_DELAYED_PROGRESS,
    STUDY_RIGHT_ALERT_TYPES,
    AcademicAlert,
    AcademicAlertGenerationResult,
)


logger = logging.getLogger("academic-copilot.telegram.notifications")

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

DeliveryStatus = Literal["delivered", "failed", "skipped"]
BatchDeliveryStatus = Literal["completed", "partial", "failed"]


class TutorRecipientResolver(Protocol):
    def list_active_tutor_recipients_for_student(
        self,
        student_id: int,
    ) -> list[dict[str, Any]]: ...


class TelegramNotificationSender(Protocol):
    def send_message(self, *, chat_id: int, text: str) -> "TelegramSendReceipt": ...


@dataclass(frozen=True)
class TutorNotificationRecipient:
    """Private, administrator-provisioned Tutor delivery context."""

    tutor_id: int
    telegram_user_id: int
    telegram_chat_id: int
    student_display_name: str


@dataclass(frozen=True)
class TelegramSendReceipt:
    """A confirmed Telegram provider acknowledgement."""

    provider_message_id: int


@dataclass(frozen=True)
class NotificationDeliveryResult:
    """One in-memory delivery attempt with no recipient identifiers exposed."""

    alert_type: str
    status: DeliveryStatus
    provider_message_ids: list[int] = field(default_factory=list)
    failure_code: str | None = None


@dataclass(frozen=True)
class NotificationBatchResult:
    """Aggregate result for one generated Issue #106 alert batch."""

    status: BatchDeliveryStatus
    attempted_count: int
    delivered_count: int
    failed_count: int
    skipped_count: int
    results: list[NotificationDeliveryResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, int | str]:
        """Return aggregate-only information suitable for workflow results/logs."""

        return {
            "status": self.status,
            "attempted_count": self.attempted_count,
            "delivered_count": self.delivered_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
        }


class TelegramApplicationSender:
    """Send through the already-initialized python-telegram-bot application.

    Scheduled workflows run in the scheduler's worker thread.  The application
    owns the Telegram client's event loop, so provider calls are marshalled
    back to that loop instead of creating another Telegram client.
    """

    def __init__(
        self,
        *,
        application: Application,
        application_loop: asyncio.AbstractEventLoop,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._application = application
        self._application_loop = application_loop
        self._timeout_seconds = timeout_seconds

    def send_message(self, *, chat_id: int, text: str) -> TelegramSendReceipt:
        future = asyncio.run_coroutine_threadsafe(
            self._application.bot.send_message(chat_id=chat_id, text=text),
            self._application_loop,
        )
        try:
            message = future.result(timeout=self._timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError("Telegram delivery timed out") from exc

        message_id = getattr(message, "message_id", None)
        if not _is_positive_int(message_id):
            raise RuntimeError("Telegram acknowledgement did not include a message ID")
        return TelegramSendReceipt(provider_message_id=message_id)


_configured_sender: TelegramNotificationSender | None = None


def configure_telegram_notification_sender(
    *,
    application: Application,
    application_loop: asyncio.AbstractEventLoop,
) -> None:
    """Register the application-owned sender after Telegram initialization."""

    global _configured_sender
    _configured_sender = TelegramApplicationSender(
        application=application,
        application_loop=application_loop,
    )


def clear_telegram_notification_sender() -> None:
    """Remove the lifecycle-bound sender during Telegram shutdown."""

    global _configured_sender
    _configured_sender = None


class AcademicAlertNotificationDelivery:
    """Resolve approved Tutors, render Issue #106 alerts, and send them."""

    def __init__(
        self,
        *,
        recipient_resolver: TutorRecipientResolver,
        sender: TelegramNotificationSender,
    ) -> None:
        self._recipient_resolver = recipient_resolver
        self._sender = sender

    def deliver(
        self,
        alert_result: AcademicAlertGenerationResult,
    ) -> NotificationBatchResult:
        if alert_result.status == "failed":
            return NotificationBatchResult(
                status="failed",
                attempted_count=0,
                delivered_count=0,
                failed_count=0,
                skipped_count=0,
                errors=["ACADEMIC_ALERT_SOURCE_FAILED"],
            )

        results: list[NotificationDeliveryResult] = []
        for alert in sorted(
            alert_result.alerts,
            key=lambda item: (
                item.affected_student_id,
                item.alert_type,
                item.occurrence_date or "",
            ),
        ):
            results.extend(self._deliver_alert(alert))

        return _batch_result(results, source_status=alert_result.status)

    def _deliver_alert(self, alert: AcademicAlert) -> list[NotificationDeliveryResult]:
        try:
            recipients = _recipients(
                self._recipient_resolver.list_active_tutor_recipients_for_student(
                    alert.affected_student_id
                )
            )
        except Exception:
            logger.exception(
                "Telegram notification recipient resolution failed: alert_type=%s",
                alert.alert_type,
            )
            return [
                NotificationDeliveryResult(
                    alert_type=alert.alert_type,
                    status="failed",
                    failure_code="RECIPIENT_RESOLUTION_FAILED",
                )
            ]

        if not recipients:
            return [
                NotificationDeliveryResult(
                    alert_type=alert.alert_type,
                    status="skipped",
                    failure_code="NO_AUTHORIZED_TUTOR_RECIPIENT",
                )
            ]

        results: list[NotificationDeliveryResult] = []
        for recipient in recipients:
            try:
                chunks = render_academic_alert(alert, recipient=recipient)
            except ValueError:
                logger.warning(
                    "Telegram notification template input was invalid: alert_type=%s",
                    alert.alert_type,
                )
                results.append(
                    NotificationDeliveryResult(
                        alert_type=alert.alert_type,
                        status="failed",
                        failure_code="TEMPLATE_INPUT_INVALID",
                    )
                )
                continue

            message_ids: list[int] = []
            try:
                for chunk in chunks:
                    receipt = self._sender.send_message(
                        chat_id=recipient.telegram_chat_id,
                        text=chunk,
                    )
                    if not _is_positive_int(receipt.provider_message_id):
                        raise RuntimeError("Telegram acknowledgement was malformed")
                    message_ids.append(receipt.provider_message_id)
            except Exception as exc:
                logger.warning(
                    "Telegram notification delivery failed: alert_type=%s failure_code=%s",
                    alert.alert_type,
                    _failure_code(exc),
                )
                results.append(
                    NotificationDeliveryResult(
                        alert_type=alert.alert_type,
                        status="failed",
                        provider_message_ids=message_ids,
                        failure_code=_failure_code(exc),
                    )
                )
                continue

            results.append(
                NotificationDeliveryResult(
                    alert_type=alert.alert_type,
                    status="delivered",
                    provider_message_ids=message_ids,
                )
            )
        return results


def create_database_academic_alert_notification_delivery(
    *,
    session: Any,
) -> AcademicAlertNotificationDelivery | None:
    """Wire delivery only when the existing Telegram application is available."""

    if _configured_sender is None:
        return None
    return AcademicAlertNotificationDelivery(
        recipient_resolver=TutorRepository(session),
        sender=_configured_sender,
    )


def render_academic_alert(
    alert: AcademicAlert,
    *,
    recipient: TutorNotificationRecipient,
) -> list[str]:
    """Render one authorized, plain-text Issue #106 alert deterministically."""

    student_name = _single_line(recipient.student_display_name)
    if not student_name:
        raise ValueError("student display name is required")

    lines = ["Academic alert", f"Student: {student_name}"]
    evidence = alert.evidence
    if alert.alert_type == ALERT_TYPE_DELAYED_PROGRESS:
        lines.extend(
            [
                "Condition: Delayed progress",
                (
                    "Confirmed progress: "
                    f"{_nonnegative_int(evidence, 'completed_ects')} ECTS completed; "
                    f"{_nonnegative_int(evidence, 'delay_ects')} ECTS below expected "
                    f"({_nonnegative_int(evidence, 'expected_ects')} ECTS)."
                ),
            ]
        )
    elif alert.alert_type in STUDY_RIGHT_ALERT_TYPES:
        lines.append(f"Condition: {_study_right_label(alert.alert_type)}")
        expiration_date = evidence.get("expiration_date")
        days_until = evidence.get("days_until_expiration")
        if isinstance(expiration_date, str) and _single_line(expiration_date):
            lines.append(f"Study-right date: {_single_line(expiration_date)}")
        if isinstance(days_until, int) and not isinstance(days_until, bool):
            lines.append(f"Days until date: {days_until}")
        extension_count = _nonnegative_int(evidence, "extension_count")
        if alert.alert_type == "STUDY_RIGHT_EXTENDED":
            lines.append(f"Recorded extensions: {extension_count}")
    elif alert.alert_type == ALERT_TYPE_ACADEMIC_RISK_DETECTED:
        severity = _risk_level(alert.severity)
        assessment_status = _assessment_status(evidence.get("assessment_status"))
        lines.extend(
            [
                f"Condition: Academic risk ({severity})",
                f"Assessment: {assessment_status.lower()} assessment",
                "Contributing indicators: " + _indicator_labels(
                    evidence.get("contributing_indicators")
                ),
            ]
        )
        unavailable = _indicator_labels(evidence.get("unavailable_indicators"))
        if unavailable:
            lines.append(f"Unavailable indicators: {unavailable}")
    else:
        raise ValueError("unsupported academic alert type")

    return split_telegram_text("\n".join(lines))


def split_telegram_text(
    text: str,
    *,
    maximum_length: int = TELEGRAM_MAX_MESSAGE_LENGTH,
) -> list[str]:
    """Split plain text deterministically without truncating content."""

    if maximum_length <= 0:
        raise ValueError("maximum_length must be positive")
    if not text:
        raise ValueError("text must not be empty")
    if len(text) <= maximum_length:
        return [text]

    chunks = _split_plain_text(text, maximum_length)
    if len(chunks) == 1:
        return chunks

    # Reserve room for ``(part/total) `` first, then split again.  Repeating
    # this handles a digit-boundary increase in the total part count without
    # ever truncating a source character.
    while True:
        prefix_length = len(f"({len(chunks)}/{len(chunks)}) ")
        if prefix_length >= maximum_length:
            raise ValueError("maximum_length is too small for numbered chunks")
        numbered_chunks = _split_plain_text(text, maximum_length - prefix_length)
        if len(str(len(numbered_chunks))) == len(str(len(chunks))):
            chunks = numbered_chunks
            break
        chunks = numbered_chunks

    total = len(chunks)
    return [f"({index}/{total}) {chunk}" for index, chunk in enumerate(chunks, start=1)]


def _split_plain_text(text: str, maximum_length: int) -> list[str]:
    """Split text at a preferred boundary while preserving every character."""

    chunks: list[str] = []
    remaining = text
    while len(remaining) > maximum_length:
        split_at = remaining.rfind("\n", 0, maximum_length + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, maximum_length + 1)
        if split_at <= 0:
            split_at = maximum_length
        elif remaining[split_at] in {"\n", " "}:
            split_at += 1
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    chunks.append(remaining)
    return chunks


def _recipients(rows: Any) -> list[TutorNotificationRecipient]:
    if not isinstance(rows, list):
        raise ValueError("recipient resolver returned malformed data")
    recipients: list[TutorNotificationRecipient] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("recipient resolver returned malformed row")
        tutor_id = row.get("tutor_id")
        user_id = row.get("telegram_user_id")
        chat_id = row.get("telegram_chat_id")
        student_name = row.get("student_display_name")
        if (
            not _is_positive_int(tutor_id)
            or not _is_positive_int(user_id)
            or not _is_positive_int(chat_id)
            or not isinstance(student_name, str)
            or not _single_line(student_name)
        ):
            continue
        recipients.append(
            TutorNotificationRecipient(
                tutor_id=tutor_id,
                telegram_user_id=user_id,
                telegram_chat_id=chat_id,
                student_display_name=_single_line(student_name),
            )
        )
    return sorted(recipients, key=lambda item: item.tutor_id)


def _batch_result(
    results: list[NotificationDeliveryResult],
    *,
    source_status: str,
) -> NotificationBatchResult:
    delivered = sum(item.status == "delivered" for item in results)
    failed = sum(item.status == "failed" for item in results)
    skipped = sum(item.status == "skipped" for item in results)
    attempted = delivered + failed
    errors = _deduplicate(
        [item.failure_code for item in results if item.failure_code is not None]
    )

    if failed and not delivered:
        status: BatchDeliveryStatus = "failed"
    elif failed or skipped or source_status == "partial":
        status = "partial"
    else:
        status = "completed"
    return NotificationBatchResult(
        status=status,
        attempted_count=attempted,
        delivered_count=delivered,
        failed_count=failed,
        skipped_count=skipped,
        results=results,
        errors=errors,
    )


def _study_right_label(alert_type: str) -> str:
    return {
        "STUDY_RIGHT_EXPIRED": "Study right expired",
        "STUDY_RIGHT_EXPIRING_SOON": "Study right expiring soon",
        "STUDY_RIGHT_EXTENDED": "Study right extended",
    }[alert_type]


def _nonnegative_int(evidence: dict[str, Any], field_name: str) -> int:
    value = evidence.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{field_name} is invalid")
    return value


def _risk_level(value: Any) -> str:
    if value not in {"MEDIUM", "HIGH", "CRITICAL"}:
        raise ValueError("risk severity is invalid")
    return value


def _assessment_status(value: Any) -> str:
    if value not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("assessment status is invalid")
    return value


def _indicator_labels(value: Any) -> str:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("indicator list is invalid")
    return ", ".join(_single_line(item).replace("_", " ") for item in value if _single_line(item))


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _failure_code(exc: Exception) -> str:
    type_name = type(exc).__name__
    if type_name in {"RetryAfter", "TimedOut", "TimeoutError"}:
        return "TELEGRAM_TIMEOUT_OR_RATE_LIMIT"
    if type_name == "Forbidden":
        return "TELEGRAM_RECIPIENT_BLOCKED"
    if type_name in {"BadRequest", "ChatMigrated"}:
        return "TELEGRAM_INVALID_RECIPIENT_OR_MESSAGE"
    return "TELEGRAM_DELIVERY_FAILED"


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
