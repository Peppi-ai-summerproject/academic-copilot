from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

# ── AgentRoute — matches routing.py SUPPORTED_ROUTES ──────────────────────────
AgentRoute = Literal[
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
    "academic_data",
    "finish",
]

# ── AgentStatus — Literal to match base.py get_args() usage ───────────────────
AgentStatus = Literal["SUCCESS", "PARTIAL", "FAILED", "SKIPPED"]


class AgentName(str, Enum):
    CALENDAR = "calendar"
    PROGRESS = "progress"
    STUDY_RIGHTS = "study_rights"
    RECOMMENDATION = "recommendation"
    COMMUNICATION = "communication"
    RISK = "risk"
    REPORTING = "reporting"


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


# ────────────────────────── AgentResult ─────────────────────────────
@dataclass
class AgentResult:
    """Standard result returned by every academic agent."""

    agent_name: str
    route: AgentRoute
    status: AgentStatus
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        valid_routes = get_args(AgentRoute)
        valid_statuses = get_args(AgentStatus)

        if self.route not in valid_routes:
            raise ValueError(f"Invalid agent route: {self.route}")

        if self.status not in valid_statuses:
            raise ValueError(f"Invalid agent status: {self.status}")
