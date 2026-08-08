"""Unit tests for the pure legacy agent risk-policy helpers."""

from datetime import date, datetime

import pytest

from app.services.risk_policy import (
    event_risk_factors,
    highest_risk_level,
    progress_risk_factors,
    study_right_risk_factors,
)


TODAY = date(2026, 8, 8)


def test_non_behind_progress_does_not_create_a_factor() -> None:
    assert progress_risk_factors({"status": "ON_TRACK"}) == []
    assert progress_risk_factors({"status": "AHEAD"}) == []


@pytest.mark.parametrize(
    ("deficit", "expected_level"),
    [(1, "LOW"), (29, "LOW"), (30, "MEDIUM"), (59, "MEDIUM"), (60, "HIGH")],
)
def test_progress_deficit_boundaries(deficit: int, expected_level: str) -> None:
    factor = progress_risk_factors({
        "status": "BEHIND",
        "completed_ects": 120 - deficit,
        "expected_ects": 120,
        "difference_ects": -deficit,
    })[0]

    assert factor["level"] == expected_level
    assert factor["values"]["ects_deficit"] == deficit


def test_progress_fallback_uses_completed_and_expected_when_difference_missing() -> None:
    factor = progress_risk_factors({
        "status": "BEHIND",
        "completed_ects": 75,
        "expected_ects": 100,
    })[0]

    assert factor["values"] == {
        "completed_ects": 75,
        "expected_ects": 100,
        "ects_deficit": 25,
    }


@pytest.mark.parametrize("safe_status", ["ACTIVE", "GRADUATED", "UNKNOWN", ""])
def test_safe_or_unsupported_study_right_status_has_no_factor(safe_status: str) -> None:
    assert study_right_risk_factors({"status": safe_status}) == []


def test_study_right_normalizes_date_and_preserves_extension_count() -> None:
    factor = study_right_risk_factors({
        "status": "EXPIRES_SOON",
        "end_date": date(2026, 9, 30),
        "extension_count": 2,
    })[0]

    assert factor["level"] == "MEDIUM"
    assert factor["values"] == {
        "status": "EXPIRES_SOON",
        "expiration_date": "2026-09-30",
        "extension_count": 2,
    }


def _event(days: int, **changes) -> dict:
    value = {
        "id": 7,
        "event_name": "Registration deadline",
        "event_type": "DEADLINE",
        "event_date": date.fromordinal(TODAY.toordinal() + days),
        "affects_all_students": True,
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(("days", "count"), [(-1, 0), (0, 1), (14, 1), (15, 0)])
def test_deadline_window_is_inclusive_and_ignores_past_events(days: int, count: int) -> None:
    factors, malformed = event_risk_factors([_event(days)], today=TODAY)

    assert len(factors) == count
    assert malformed is False


def test_datetime_event_is_normalized_to_date() -> None:
    event = _event(2, event_date=datetime(2026, 8, 10, 14, 30))
    factors, malformed = event_risk_factors([event], today=TODAY)

    assert malformed is False
    assert factors[0]["values"]["event_date"] == "2026-08-10"
    assert factors[0]["values"]["days_until_event"] == 2


def test_malformed_event_is_disclosed_without_hiding_valid_event() -> None:
    factors, malformed = event_risk_factors(
        [{"event_type": "DEADLINE", "event_date": "not-a-date"}, _event(3)],
        today=TODAY,
    )

    assert malformed is True
    assert len(factors) == 1
    assert factors[0]["values"]["days_until_event"] == 3


def test_non_global_or_non_deadline_event_is_ignored_without_malformed_flag() -> None:
    factors, malformed = event_risk_factors(
        [_event(2, affects_all_students=False), _event(2, event_type="INFO")],
        today=TODAY,
    )

    assert factors == []
    assert malformed is False


def test_highest_risk_level_uses_default_and_priority_order() -> None:
    assert highest_risk_level([]) == "NONE"
    assert highest_risk_level([], default="LOW") == "LOW"
    assert highest_risk_level([
        {"level": "LOW"},
        {"level": "HIGH"},
        {"level": "MEDIUM"},
    ]) == "HIGH"
