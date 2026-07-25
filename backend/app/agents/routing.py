from __future__ import annotations

from typing import Mapping

from app.agents.types import AgentRoute

SUPPORTED_ROUTES: tuple[AgentRoute, ...] = (
    "calendar",
    "progress",
    "study_rights",
    "risk",
    "recommendation",
    "reporting",
    "communication",
    "finish",
)

AGENT_ROUTE_TO_AGENT_NAME: Mapping[AgentRoute, str] = {
    "calendar": "CalendarAgent",
    "progress": "ProgressAnalysisAgent",
    "study_rights": "StudyRightsAgent",
    "risk": "RiskDetectionAgent",
    "recommendation": "RecommendationAgent",
    "reporting": "ReportingAgent",
    "communication": "CommunicationAgent",
    "finish": "Finish",
}

ROUTE_INTENT_MAP: Mapping[str, AgentRoute] = {
    "calendar": "calendar",
    "upcoming events": "calendar",
    "academic deadline": "calendar",
    "progress": "progress",
    "study rights": "study_rights",
    "risk": "risk",
    "recommendation": "recommendation",
    "report": "reporting",
    "reporting": "reporting",
    "communication": "communication",
}
