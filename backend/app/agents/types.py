"""Common types for the multi-agent system — Issue #87."""

from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class AgentName(str, Enum):
    CALENDAR = "calendar"
    PROGRESS = "progress"
    STUDY_RIGHTS = "study_rights"
    RECOMMENDATION = "recommendation"
    COMMUNICATION = "communication"
    RISK = "risk"
    REPORTING = "reporting"


class AgentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class EvidenceItem(BaseModel):
    """A single piece of evidence supporting an agent finding."""
    source: str
    tool_name: str = ""
    reference: str = ""
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    model_config = {"frozen": True}


class AgentResult(BaseModel):
    """Structured result produced by a single agent during workflow execution."""
    agent_name: str
    status: AgentStatus
    summary: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    model_config = {"frozen": True}

    def is_successful(self) -> bool:
        return self.status in (AgentStatus.SUCCESS, AgentStatus.PARTIAL)

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def has_errors(self) -> bool:
        return len(self.errors) > 0
