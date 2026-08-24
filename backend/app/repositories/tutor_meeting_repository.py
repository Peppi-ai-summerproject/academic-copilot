"""Database access for student-specific tutor meetings."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class TutorMeetingRepository:
    """Retrieve authoritative meeting records without applying risk policy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_student_window(
        self,
        student_id: int,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        # This read is optional evidence in larger workflows that deliberately
        # share one Session.  A database-level error (for example, a deployment
        # that has not yet received the compatibility migration) must therefore
        # roll back to a savepoint instead of aborting the caller's transaction.
        # The repository does not own the Session and must not roll it back in
        # full.
        with self._session.begin_nested():
            rows = self._session.execute(
                text(
                    """
                SELECT
                    id,
                    student_id,
                    tutor_id,
                    status,
                    scheduled_at,
                    completed_at,
                    cancelled_at
                FROM tutor_meetings
                WHERE student_id = :student_id
                  AND (scheduled_at AT TIME ZONE 'UTC')::date
                      BETWEEN :start_date AND :end_date
                ORDER BY scheduled_at ASC, id ASC
                    """
                ),
                {
                    "student_id": student_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).mappings().all()
        return [dict(row) for row in rows]
