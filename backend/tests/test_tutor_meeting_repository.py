from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.tutor_meeting_repository import TutorMeetingRepository


def test_lists_student_meetings_with_inclusive_boundaries_and_stable_order():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {"id": 1, "student_id": 7, "status": "COMPLETED"}
    ]

    result = TutorMeetingRepository(session).list_for_student_window(
        7, start_date=date(2026, 5, 7), end_date=date(2026, 9, 4)
    )

    assert result == [{"id": 1, "student_id": 7, "status": "COMPLETED"}]
    statement, parameters = session.execute.call_args.args
    assert "student_id = :student_id" in statement.text
    assert "BETWEEN :start_date AND :end_date" in statement.text
    assert "AT TIME ZONE 'UTC'" in statement.text
    assert "ORDER BY scheduled_at ASC, id ASC" in statement.text
    assert parameters == {
        "student_id": 7,
        "start_date": date(2026, 5, 7),
        "end_date": date(2026, 9, 4),
    }


def test_successful_empty_query_returns_empty_list():
    session = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []
    assert TutorMeetingRepository(session).list_for_student_window(
        1, start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
    ) == []


def test_database_failure_propagates():
    session = MagicMock()
    session.execute.side_effect = SQLAlchemyError("database unavailable")
    with pytest.raises(SQLAlchemyError):
        TutorMeetingRepository(session).list_for_student_window(
            1, start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
        )
    session.begin_nested.assert_called_once_with()
    session.rollback.assert_not_called()


def test_failed_optional_query_is_scoped_to_savepoint_so_later_query_can_run():
    class Savepoint:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self

        def __exit__(self, _type, _value, _traceback):
            self.session.failed = False
            return False

    class PostgreSQLLikeSession:
        def __init__(self):
            self.failed = False

        def begin_nested(self):
            return Savepoint(self)

        def execute(self, statement, _parameters=None):
            if "FROM tutor_meetings" in statement.text:
                self.failed = True
                raise SQLAlchemyError("undefined column")
            if self.failed:
                raise SQLAlchemyError("current transaction is aborted")
            return "later query succeeded"

    session = PostgreSQLLikeSession()
    with pytest.raises(SQLAlchemyError, match="undefined column"):
        TutorMeetingRepository(session).list_for_student_window(
            1, start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
        )

    assert session.execute(type("Statement", (), {"text": "SELECT 1"})()) == (
        "later query succeeded"
    )
