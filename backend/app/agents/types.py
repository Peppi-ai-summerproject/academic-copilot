"""Common types for the multi-agent system — Issues #87, #81, #82."""

from __future__ import annotations
from enum import Enum
from typing import Any, Literal
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


# ── AgentState forward reference for base.py Protocol ─────────────────────────
# base.py imports AgentState from here for the AcademicAgent Protocol.
# The full implementation is in app.agents.state to avoid circular imports.
# Agents import AgentState from app.agents.state directly.
class AgentState:
    """Minimal AgentState for Protocol type checking.

    Full implementation: app.agents.state.AgentState
    Agents must import from app.agents.state, not from here.
    """
    pass
