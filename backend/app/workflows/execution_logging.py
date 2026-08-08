"""Privacy-safe, durable execution-history support for Issue #108.

This module records workflow lifecycle metadata only.  It deliberately does
not serialize workflow result objects, student-scoped data, rendered messages,
or exception text.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol, TypeVar


logger = logging.getLogger("academic-copilot.workflows.execution_logging")

ExecutionStatus = Literal["running", "completed", "partial", "failed", "unavailable"]
FinalExecutionStatus = Literal["completed", "partial", "failed", "unavailable"]
TriggerType = Literal["direct", "scheduler", "workflow"]

_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_:-]{0,159}$")
_active_execution: ContextVar["WorkflowExecutionContext | None"] = ContextVar(
    "active_workflow_execution",
    default=None,
)
_Result = TypeVar("_Result")


@dataclass(frozen=True)
class WorkflowExecutionLog:
    """The fixed, aggregate-only data allowed in durable workflow history."""

    execution_id: uuid.UUID
    correlation_id: uuid.UUID
    parent_execution_id: uuid.UUID | None
    workflow_name: str
    execution_key: str | None
    trigger_type: TriggerType
    status: ExecutionStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = None
    requested_count: int | None = None
    processed_count: int | None = None
    succeeded_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    warning_count: int = 0
    error_count: int = 0
    safe_error_code: str | None = None
    safe_error_summary: str | None = None


class WorkflowExecutionLogStore(Protocol):
    """Persistence boundary used by the recorder and in-memory test doubles."""

    def start_execution(self, record: WorkflowExecutionLog) -> None:
        """Persist a running record, or raise without exposing unsafe details."""

    def finalize_execution(self, record: WorkflowExecutionLog) -> None:
        """Persist a final record, inserting it if the start write was unavailable."""


@dataclass(frozen=True)
class WorkflowExecutionContext:
    """In-memory correlation context; it is never stored as arbitrary state."""

    execution_id: uuid.UUID
    correlation_id: uuid.UUID
    parent_execution_id: uuid.UUID | None
    workflow_name: str
    execution_key: str | None
    trigger_type: TriggerType
    started_at: datetime
    started_monotonic_ns: int


@dataclass(frozen=True)
class WorkflowExecutionOutcome:
    """Sanitized final outcome supplied by a workflow-specific adapter."""

    status: FinalExecutionStatus
    requested_count: int | None = None
    processed_count: int | None = None
    succeeded_count: int | None = None
    failed_count: int | None = None
    skipped_count: int | None = None
    warning_count: int = 0
    error_count: int = 0
    safe_error_code: str | None = None
    safe_error_summary: str | None = None


def workflow_outcome(
    *,
    status: object,
    requested_count: object = None,
    processed_count: object = None,
    succeeded_count: object = None,
    failed_count: object = None,
    skipped_count: object = None,
    warnings: object = None,
    errors: object = None,
) -> WorkflowExecutionOutcome:
    """Build a fixed, sanitized outcome without retaining raw workflow values."""

    final_status: FinalExecutionStatus
    if status in {"completed", "partial", "failed", "unavailable"}:
        final_status = status
    else:
        final_status = "failed"

    warning_count = _string_item_count(warnings)
    error_values = _safe_error_values(errors)
    error_count = _string_item_count(errors)
    safe_error_code = error_values[0] if error_values else None
    safe_error_summary = (
        "Workflow reported one or more safe error codes."
        if safe_error_code is not None
        else (
            "Workflow reported one or more errors."
            if error_count
            else None
        )
    )

    return WorkflowExecutionOutcome(
        status=final_status,
        requested_count=_count_or_none(requested_count),
        processed_count=_count_or_none(processed_count),
        succeeded_count=_count_or_none(succeeded_count),
        failed_count=_count_or_none(failed_count),
        skipped_count=_count_or_none(skipped_count),
        warning_count=warning_count,
        error_count=error_count,
        safe_error_code=safe_error_code,
        safe_error_summary=safe_error_summary,
    )


class WorkflowExecutionRecorder:
    """Best-effort recorder that never changes a workflow's business result."""

    def __init__(
        self,
        store: WorkflowExecutionLogStore,
        *,
        now: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic_ns = monotonic_ns or time.perf_counter_ns

    def run(
        self,
        *,
        workflow_name: str,
        execution_key: str | None,
        trigger_type: TriggerType,
        operation: Callable[[], _Result],
        outcome_for: Callable[[_Result], WorkflowExecutionOutcome],
    ) -> _Result:
        """Run an operation while recording start and final aggregate outcome."""

        context = self._start(
            workflow_name=workflow_name,
            execution_key=execution_key,
            trigger_type=trigger_type,
        )
        token = _active_execution.set(context)
        try:
            result = operation()
        except Exception:
            self._finish(
                context,
                WorkflowExecutionOutcome(
                    status="failed",
                    error_count=1,
                    safe_error_code="WORKFLOW_EXECUTION_FAILED",
                    safe_error_summary="Workflow raised before producing a result.",
                ),
            )
            raise
        else:
            try:
                outcome = outcome_for(result)
            except Exception:
                logger.warning(
                    "Workflow history outcome mapping failed: workflow_name=%s execution_id=%s",
                    context.workflow_name,
                    context.execution_id,
                )
                outcome = WorkflowExecutionOutcome(
                    status="failed",
                    error_count=1,
                    safe_error_code="WORKFLOW_OUTCOME_UNAVAILABLE",
                    safe_error_summary="Workflow returned an unsupported outcome.",
                )
            self._finish(context, outcome)
            return result
        finally:
            _active_execution.reset(token)

    def _start(
        self,
        *,
        workflow_name: str,
        execution_key: str | None,
        trigger_type: TriggerType,
    ) -> WorkflowExecutionContext:
        parent = _active_execution.get()
        execution_id = uuid.uuid4()
        started_at = _utc_now(self._now)
        context = WorkflowExecutionContext(
            execution_id=execution_id,
            correlation_id=parent.correlation_id if parent else execution_id,
            parent_execution_id=parent.execution_id if parent else None,
            workflow_name=_workflow_name(workflow_name),
            execution_key=_execution_key(execution_key),
            trigger_type="workflow" if parent else trigger_type,
            started_at=started_at,
            started_monotonic_ns=self._monotonic_ns(),
        )
        try:
            self._store.start_execution(
                WorkflowExecutionLog(
                    execution_id=context.execution_id,
                    correlation_id=context.correlation_id,
                    parent_execution_id=context.parent_execution_id,
                    workflow_name=context.workflow_name,
                    execution_key=context.execution_key,
                    trigger_type=context.trigger_type,
                    status="running",
                    started_at=context.started_at,
                )
            )
        except Exception:
            logger.warning(
                "Workflow history start persistence failed: workflow_name=%s execution_id=%s",
                context.workflow_name,
                context.execution_id,
            )
        return context

    def _finish(
        self,
        context: WorkflowExecutionContext,
        outcome: WorkflowExecutionOutcome,
    ) -> None:
        completed_at = _utc_now(self._now)
        duration_ms = max(0, (self._monotonic_ns() - context.started_monotonic_ns) // 1_000_000)
        record = WorkflowExecutionLog(
            execution_id=context.execution_id,
            correlation_id=context.correlation_id,
            parent_execution_id=context.parent_execution_id,
            workflow_name=context.workflow_name,
            execution_key=context.execution_key,
            trigger_type=context.trigger_type,
            status=outcome.status,
            started_at=context.started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            requested_count=outcome.requested_count,
            processed_count=outcome.processed_count,
            succeeded_count=outcome.succeeded_count,
            failed_count=outcome.failed_count,
            skipped_count=outcome.skipped_count,
            warning_count=outcome.warning_count,
            error_count=outcome.error_count,
            safe_error_code=outcome.safe_error_code,
            safe_error_summary=outcome.safe_error_summary,
        )
        try:
            self._store.finalize_execution(record)
        except Exception:
            logger.warning(
                "Workflow history final persistence failed: workflow_name=%s execution_id=%s",
                context.workflow_name,
                context.execution_id,
            )


def _count_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _string_item_count(value: object) -> int:
    if not isinstance(value, (list, tuple)):
        return 0
    return sum(isinstance(item, str) for item in value)


def _safe_error_values(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    values: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.rsplit(":", 1)[-1]
        if _SAFE_CODE.fullmatch(candidate):
            values.append(candidate)
    return list(dict.fromkeys(values))


def _workflow_name(value: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ValueError("workflow_name must be a safe identifier")
    return value


def _execution_key(value: str | None) -> str | None:
    if value is None:
        return None
    if not _SAFE_IDENTIFIER.fullmatch(value):
        return None
    return value


def _utc_now(now: Callable[[], datetime]) -> datetime:
    value = now()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
