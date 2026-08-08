"""Persistence for non-sensitive aggregate weekly workflow reports."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class WeeklyReportRepository:
    """Store one aggregate report for each deterministic weekly execution key."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_report(
        self,
        *,
        workflow_name: str,
        execution_key: str,
        period_start: date,
        period_end: date,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        report_payload: dict[str, Any],
    ) -> dict[str, int | str]:
        """Save the report once, returning whether this execution already exists.

        The unique execution key is a durable idempotency boundary for stored
        reports. It deliberately does not act as a distributed execution lock:
        more than one application instance can still compute the same report.
        """

        try:
            row = self._session.execute(
                text(
                    """
                    INSERT INTO weekly_workflow_reports (
                        workflow_name,
                        execution_key,
                        period_start,
                        period_end,
                        started_at,
                        completed_at,
                        status,
                        report_payload
                    )
                    VALUES (
                        :workflow_name,
                        :execution_key,
                        :period_start,
                        :period_end,
                        :started_at,
                        :completed_at,
                        :status,
                        CAST(:report_payload AS jsonb)
                    )
                    ON CONFLICT (execution_key) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "workflow_name": workflow_name,
                    "execution_key": execution_key,
                    "period_start": period_start,
                    "period_end": period_end,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "status": status,
                    "report_payload": json.dumps(
                        report_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                },
            ).mappings().first()

            if row is not None:
                self._session.commit()
                return {"status": "saved", "report_id": int(row["id"])}

            existing_id = self._session.execute(
                text(
                    """
                    SELECT id
                    FROM weekly_workflow_reports
                    WHERE execution_key = :execution_key
                    """
                ),
                {"execution_key": execution_key},
            ).scalar_one()
            self._session.commit()
            return {"status": "already_stored", "report_id": int(existing_id)}
        except SQLAlchemyError:
            self._session.rollback()
            raise
