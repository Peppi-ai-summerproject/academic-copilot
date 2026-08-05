import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.tutor_meeting_risk_service import TutorMeetingRiskService


AS_OF = date(2026, 8, 5)


class Repository:
    def __init__(self, rows=None, error=None):
        self.rows = [] if rows is None else rows
        self.error = error
        self.calls = []

    def list_for_student_window(self, student_id, *, start_date, end_date):
        self.calls.append((student_id, start_date, end_date))
        if self.error:
            raise self.error
        return self.rows


def meeting(status, days, *, meeting_id=1, student_id=1, **extra):
    scheduled = datetime.combine(
        AS_OF + timedelta(days=days), datetime.min.time(), timezone.utc
    )
    value = {
        "id": meeting_id,
        "student_id": student_id,
        "tutor_id": 2,
        "status": status,
        "scheduled_at": scheduled,
        "completed_at": scheduled if status == "COMPLETED" else None,
        "cancelled_at": scheduled if status == "CANCELLED" else None,
    }
    value.update(extra)
    return value


def evaluate(*rows, as_of=AS_OF):
    repository = Repository(list(rows))
    result = TutorMeetingRiskService(repository).evaluate_student(1, as_of_date=as_of)
    return result, repository


@pytest.mark.parametrize(("row", "points", "rule"), [
    (meeting("COMPLETED", -1), 0, "RECENT_TUTOR_MEETING_COMPLETED"),
    (meeting("SCHEDULED", 1), 5, "TUTOR_MEETING_UPCOMING_WITHOUT_RECENT_COMPLETION"),
    (meeting("MISSED", -1), 10, "TUTOR_MEETING_MISSED"),
])
def test_basic_scoring(row, points, rule):
    result, _ = evaluate(row)
    assert result["evaluation_status"] == "EVALUATED"
    assert (result["assigned_points"], result["matched_rule_code"]) == (points, rule)


def test_later_completed_supersedes_earlier_missed():
    result, _ = evaluate(meeting("MISSED", -10), meeting("COMPLETED", -2, meeting_id=2))
    assert result["assigned_points"] == 0


def test_later_missed_takes_precedence_over_older_completed():
    result, _ = evaluate(meeting("COMPLETED", -10), meeting("MISSED", -2, meeting_id=2))
    assert result["assigned_points"] == 10


@pytest.mark.parametrize("rows", [
    (meeting("CANCELLED", -1),),
    (),
    (meeting("SCHEDULED", -1),),
])
def test_cancelled_empty_and_overdue_scheduled_are_unavailable(rows):
    result, _ = evaluate(*rows)
    assert result == {
        "success": False,
        "evaluation_status": "UNAVAILABLE",
        "assigned_points": None,
        "matched_rule_code": "TUTOR_MEETING_EVIDENCE_UNAVAILABLE",
        "normalized_input": {},
    }


@pytest.mark.parametrize("row", [
    meeting("UNKNOWN", -1),
    meeting("COMPLETED", -1, scheduled_at="2026-08-04"),
    meeting("COMPLETED", -1, completed_at=None),
])
def test_unsupported_or_malformed_evidence_is_unavailable(row):
    result, _ = evaluate(row)
    assert result["evaluation_status"] == "UNAVAILABLE"


def test_exact_window_boundaries_and_explicit_as_of_date():
    completed, repository = evaluate(meeting("COMPLETED", -90))
    upcoming, _ = evaluate(meeting("SCHEDULED", 30))
    assert completed["assigned_points"] == 0
    assert upcoming["assigned_points"] == 5
    assert repository.calls == [(1, date(2026, 5, 7), date(2026, 9, 4))]


def test_repository_failure_is_unavailable():
    result = TutorMeetingRiskService(Repository(error=RuntimeError("down"))).evaluate_student(
        1, as_of_date=AS_OF
    )
    assert result["evaluation_status"] == "UNAVAILABLE"


def test_normalized_output_excludes_private_and_personal_data():
    row = meeting(
        "COMPLETED", -1, private_notes="secret", student_name="Private", telegram_user_id=9
    )
    result, _ = evaluate(row)
    encoded = json.dumps(result)
    assert "secret" not in encoded
    assert "Private" not in encoded
    assert "telegram" not in encoded
