"""Deterministic project heuristics for academic risk assessment.

These rules support the academic-copilot demonstration. They are not an
official university policy.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


DEADLINE_EVENT_TYPES = frozenset({"DEADLINE"})
DEADLINE_RISK_WINDOW_DAYS = 14
_RISK_ORDER = {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


def progress_risk_factors(progress: dict[str, Any]) -> list[dict[str, Any]]:
    if str(progress.get("status", "")).upper() != "BEHIND":
        return []

    completed = progress.get("completed_ects", 0) or 0
    expected = progress.get("expected_ects", 0) or 0
    difference = progress.get("difference_ects")
    deficit = abs(difference) if difference is not None else max(expected - completed, 0)
    level = "HIGH" if deficit >= 60 else "MEDIUM" if deficit >= 30 else "LOW"
    return [
        {
            "dimension": "progress",
            "level": level,
            "reason": f"Student is {deficit} ECTS behind expected progress.",
            "values": {
                "completed_ects": completed,
                "expected_ects": expected,
                "ects_deficit": deficit,
            },
            "evidence_source": "get_progress",
        },
    ]


def study_right_risk_factors(study_right: dict[str, Any]) -> list[dict[str, Any]]:
    status = str(study_right.get("status", "")).upper()
    level = "HIGH" if status == "EXPIRED" else "MEDIUM" if status in {
        "EXPIRES_SOON", "EXTENDED"
    } else None
    if level is None:
        return []

    reason = {
        "EXPIRED": "Study right has expired.",
        "EXPIRES_SOON": "Study right is expiring soon.",
        "EXTENDED": "Study right has been extended.",
    }[status]
    expiration_date = study_right.get("expiration_date") or study_right.get("end_date")
    if hasattr(expiration_date, "isoformat"):
        expiration_date = expiration_date.isoformat()
    return [
        {
            "dimension": "study_right",
            "level": level,
            "reason": reason,
            "values": {
                "status": status,
                "expiration_date": expiration_date,
                "extension_count": study_right.get("extension_count", 0) or 0,
            },
            "evidence_source": "get_study_right",
        },
    ]


def event_risk_factors(
    events: list[dict[str, Any]],
    *,
    today: date,
) -> tuple[list[dict[str, Any]], bool]:
    factors: list[dict[str, Any]] = []
    malformed = False
    for event in events:
        if not isinstance(event, dict):
            malformed = True
            continue
        event_type = str(event.get("event_type", "")).upper()
        if event_type not in DEADLINE_EVENT_TYPES:
            continue
        event_date = _parse_date(event.get("event_date"))
        if event_date is None:
            malformed = True
            continue
        days_until = (event_date - today).days
        if not 0 <= days_until <= DEADLINE_RISK_WINDOW_DAYS:
            continue
        if not event.get("affects_all_students", False):
            continue
        factors.append(
            {
                "dimension": "academic_event",
                "level": "MEDIUM",
                "reason": "Global academic deadline occurring within 14 days.",
                "values": {
                    "event_id": event.get("id"),
                    "event_name": event.get("event_name"),
                    "event_type": event_type,
                    "event_date": event_date.isoformat(),
                    "days_until_event": days_until,
                    "globally_applicable": True,
                },
                "evidence_source": "get_upcoming_events",
            },
        )
    return factors, malformed


def highest_risk_level(
    factors: list[dict[str, Any]],
    *,
    default: str = "NONE",
) -> str:
    return max(
        (str(factor["level"]) for factor in factors),
        key=lambda level: _RISK_ORDER[level],
        default=default,
    )


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None
