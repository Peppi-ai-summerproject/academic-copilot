"""PostgreSQL persistence for Issue #108's aggregate workflow history."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.workflows.execution_logging import WorkflowExecutionLog


class WorkflowExecutionLogRepository:
    """Store one mutable, privacy-safe record for each execution UUID."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def start_execution(self, record: WorkflowExecutionLog) -> None:
        try:
            row = self._session.execute(
                text(
                    """
                    INSERT INTO workflow_execution_logs (
                        execution_id, correlation_id, parent_execution_id,
                        workflow_name, execution_key, trigger_type, status,
                        started_at, warning_count, error_count
                    )
                    VALUES (
                        :execution_id, :correlation_id, :parent_execution_id,
                        :workflow_name, :execution_key, :trigger_type, :status,
                        :started_at, :warning_count, :error_count
                    )
                    ON CONFLICT (execution_id) DO NOTHING
                    RETURNING id
                    """
                ),
                _parameters(record),
            ).scalar_one_or_none()
            if row is None:
                self._session.rollback()
                raise RuntimeError("Workflow execution identifier already exists")
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def finalize_execution(self, record: WorkflowExecutionLog) -> None:
        """Finalize a running record or insert its final form after start failure."""

        try:
            updated = self._session.execute(
                text(
                    """
                    UPDATE workflow_execution_logs
                    SET
                        status = :status,
                        completed_at = :completed_at,
                        duration_ms = :duration_ms,
                        requested_count = :requested_count,
                        processed_count = :processed_count,
                        succeeded_count = :succeeded_count,
                        failed_count = :failed_count,
                        skipped_count = :skipped_count,
                        warning_count = :warning_count,
                        error_count = :error_count,
                        safe_error_code = :safe_error_code,
                        safe_error_summary = :safe_error_summary
                    WHERE execution_id = :execution_id AND status = 'running'
                    """
                ),
                _parameters(record),
            ).rowcount
            if updated:
                self._session.commit()
                return

            inserted = self._session.execute(
                text(
                    """
                    INSERT INTO workflow_execution_logs (
                        execution_id, correlation_id, parent_execution_id,
                        workflow_name, execution_key, trigger_type, status,
                        started_at, completed_at, duration_ms,
                        requested_count, processed_count, succeeded_count,
                        failed_count, skipped_count, warning_count, error_count,
                        safe_error_code, safe_error_summary
                    )
                    VALUES (
                        :execution_id, :correlation_id, :parent_execution_id,
                        :workflow_name, :execution_key, :trigger_type, :status,
                        :started_at, :completed_at, :duration_ms,
                        :requested_count, :processed_count, :succeeded_count,
                        :failed_count, :skipped_count, :warning_count, :error_count,
                        :safe_error_code, :safe_error_summary
                    )
                    ON CONFLICT (execution_id) DO NOTHING
                    RETURNING id
                    """
                ),
                _parameters(record),
            ).scalar_one_or_none()
            if inserted is None:
                self._session.rollback()
                raise RuntimeError("Workflow execution identifier is already finalized")
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise


def _parameters(record: WorkflowExecutionLog) -> dict[str, Any]:
    return {
        "execution_id": record.execution_id,
        "correlation_id": record.correlation_id,
        "parent_execution_id": record.parent_execution_id,
        "workflow_name": record.workflow_name,
        "execution_key": record.execution_key,
        "trigger_type": record.trigger_type,
        "status": record.status,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "duration_ms": record.duration_ms,
        "requested_count": record.requested_count,
        "processed_count": record.processed_count,
        "succeeded_count": record.succeeded_count,
        "failed_count": record.failed_count,
        "skipped_count": record.skipped_count,
        "warning_count": record.warning_count,
        "error_count": record.error_count,
        "safe_error_code": record.safe_error_code,
        "safe_error_summary": record.safe_error_summary,
    }
