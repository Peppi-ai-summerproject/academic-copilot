"""Deterministic tutor-meeting evaluation for the academic risk model."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol


LOOKBACK_DAYS = 90
UPCOMING_DAYS = 30
SUPPORTED_STATUSES = frozenset({"SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"})


class TutorMeetingReader(Protocol):
    def list_for_student_window(
        self, student_id: int, *, start_date: date, end_date: date
    ) -> list[dict[str, Any]]: ...


class TutorMeetingRiskService:
    """Normalize authoritative meeting history into the Issue #95 adapter."""

    def __init__(self, repository: TutorMeetingReader) -> None:
        self._repository = repository

    def evaluate_student(
        self, student_id: int, *, as_of_date: date
    ) -> dict[str, Any]:
        if not isinstance(student_id, int) or isinstance(student_id, bool) or student_id <= 0:
            return _unavailable()
        if not isinstance(as_of_date, date) or isinstance(as_of_date, datetime):
            return _unavailable()

        lookback_start = as_of_date - timedelta(days=LOOKBACK_DAYS)
        upcoming_end = as_of_date + timedelta(days=UPCOMING_DAYS)
        try:
            rows = self._repository.list_for_student_window(
                student_id,
                start_date=lookback_start,
                end_date=upcoming_end,
            )
        except Exception:
            return _unavailable()
        if not isinstance(rows, list) or not rows:
            return _unavailable()

        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = _normalize_row(row, student_id)
            if item is None:
                return _unavailable()
            if not lookback_start <= item["scheduled_date"] <= upcoming_end:
                return _unavailable()
            normalized.append(item)

        decisive = [
            item for item in normalized
            if item["status"] in {"COMPLETED", "MISSED"}
            and lookback_start <= item["scheduled_date"] <= as_of_date
        ]
        if decisive:
            latest = max(decisive, key=lambda item: (item["scheduled_at"], item["id"]))
            if latest["status"] == "MISSED":
                return _evaluated(10, "TUTOR_MEETING_MISSED", latest, lookback_start, upcoming_end)
            return _evaluated(
                0, "RECENT_TUTOR_MEETING_COMPLETED", latest, lookback_start, upcoming_end
            )

        upcoming = [
            item for item in normalized
            if item["status"] == "SCHEDULED"
            and as_of_date <= item["scheduled_date"] <= upcoming_end
        ]
        if upcoming:
            earliest = min(upcoming, key=lambda item: (item["scheduled_at"], item["id"]))
            return _evaluated(
                5,
                "TUTOR_MEETING_UPCOMING_WITHOUT_RECENT_COMPLETION",
                earliest,
                lookback_start,
                upcoming_end,
            )
        return _unavailable()


def _normalize_row(value: Any, student_id: int) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("student_id") != student_id:
        return None
    meeting_id = value.get("id")
    status = value.get("status")
    scheduled_at = value.get("scheduled_at")
    completed_at = value.get("completed_at")
    cancelled_at = value.get("cancelled_at")
    if not isinstance(meeting_id, int) or isinstance(meeting_id, bool):
        return None
    if status not in SUPPORTED_STATUSES or not _aware_datetime(scheduled_at):
        return None
    if completed_at is not None and not _aware_datetime(completed_at):
        return None
    if cancelled_at is not None and not _aware_datetime(cancelled_at):
        return None
    if status == "COMPLETED":
        if completed_at is None or cancelled_at is not None:
            return None
    elif status == "CANCELLED":
        if cancelled_at is None or completed_at is not None:
            return None
    elif completed_at is not None or cancelled_at is not None:
        return None
    scheduled_utc = scheduled_at.astimezone(timezone.utc)
    return {
        "id": meeting_id,
        "status": status,
        "scheduled_at": scheduled_utc,
        "scheduled_date": scheduled_utc.date(),
    }


def _aware_datetime(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _evaluated(
    points: int,
    rule: str,
    evidence: dict[str, Any],
    lookback_start: date,
    upcoming_end: date,
) -> dict[str, Any]:
    return {
        "success": True,
        "evaluation_status": "EVALUATED",
        "assigned_points": points,
        "matched_rule_code": rule,
        "normalized_input": {
            "meeting_id": evidence["id"],
            "meeting_status": evidence["status"],
            "scheduled_at": evidence["scheduled_at"].isoformat(),
            "lookback_start": lookback_start.isoformat(),
            "upcoming_end": upcoming_end.isoformat(),
        },
    }


def _unavailable() -> dict[str, Any]:
    return {
        "success": False,
        "evaluation_status": "UNAVAILABLE",
        "assigned_points": None,
        "matched_rule_code": "TUTOR_MEETING_EVIDENCE_UNAVAILABLE",
        "normalized_input": {},
    }
