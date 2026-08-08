"""Predefined academic scenarios for Issue #116 recommendation evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PolicyMode = Literal["available", "unavailable"]


@dataclass(frozen=True)
class RecommendationScenario:
    scenario_id: str
    description: str
    risk_level: str
    risk_factors: tuple[dict, ...]
    expected_types: tuple[str, ...]
    expected_interventions: tuple[str, ...]
    assessment_complete: bool = True
    unavailable_dimensions: tuple[str, ...] = ()
    policy_mode: PolicyMode = "available"


def progress_factor(deficit: int) -> dict:
    level = "HIGH" if deficit >= 60 else "MEDIUM" if deficit >= 30 else "LOW"
    expected = 120
    return {
        "dimension": "progress",
        "level": level,
        "reason": f"Student is {deficit} ECTS behind expected progress.",
        "values": {
            "completed_ects": expected - deficit,
            "expected_ects": expected,
            "ects_deficit": deficit,
        },
        "evidence_source": "get_progress",
    }


def study_right_factor(status: str = "EXPIRES_SOON") -> dict:
    level = "HIGH" if status == "EXPIRED" else "MEDIUM"
    return {
        "dimension": "study_right",
        "level": level,
        "reason": (
            "Study right has expired."
            if status == "EXPIRED"
            else "Study right is expiring soon."
        ),
        "values": {
            "status": status,
            "expiration_date": "2026-09-30",
            "extension_count": 0,
        },
        "evidence_source": "get_study_right",
    }


SCENARIOS = (
    RecommendationScenario(
        "healthy_on_track",
        "On-track student with a complete assessment and no risk factors.",
        "NONE",
        (),
        ("monitoring",),
        ("MONITOR_PROGRESS",),
    ),
    RecommendationScenario(
        "moderate_delay",
        "Student at the 30 ECTS boundary for medium progress concern.",
        "MEDIUM",
        (progress_factor(30),),
        ("progress", "progress"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING"),
    ),
    RecommendationScenario(
        "significant_delay",
        "Student at the 60 ECTS boundary for high progress concern.",
        "HIGH",
        (progress_factor(60),),
        ("progress", "progress"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING"),
    ),
    RecommendationScenario(
        "study_right_concern",
        "Study right is expiring soon while progress is not the primary concern.",
        "MEDIUM",
        (study_right_factor(),),
        ("study_right",),
        ("REVIEW_STUDY_RIGHT",),
    ),
    RecommendationScenario(
        "multiple_risk_factors",
        "Student has both a high progress deficit and an expiring study right.",
        "HIGH",
        (progress_factor(60), study_right_factor()),
        ("progress", "progress", "study_right"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING", "REVIEW_STUDY_RIGHT"),
    ),
    RecommendationScenario(
        "partial_data",
        "Confirmed progress concern with tutor-meeting evidence unavailable.",
        "MEDIUM",
        (progress_factor(30),),
        ("progress", "progress"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING"),
        assessment_complete=False,
        unavailable_dimensions=("tutor_meetings",),
    ),
    RecommendationScenario(
        "minimal_delay_no_escalation",
        "One ECTS deficit, below the tutor-meeting escalation boundary.",
        "LOW",
        (progress_factor(1),),
        ("progress",),
        ("REVIEW_STUDY_PLAN",),
    ),
    RecommendationScenario(
        "policy_supported",
        "Moderate progress concern with deterministic policy evidence.",
        "MEDIUM",
        (progress_factor(30),),
        ("progress", "progress"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING"),
    ),
    RecommendationScenario(
        "policy_unavailable",
        "Moderate progress concern when policy retrieval is unavailable.",
        "MEDIUM",
        (progress_factor(30),),
        ("progress", "progress"),
        ("REVIEW_STUDY_PLAN", "SCHEDULE_TUTOR_MEETING"),
        policy_mode="unavailable",
    ),
    RecommendationScenario(
        "boundary_29_ects",
        "Twenty-nine ECTS deficit immediately below medium escalation.",
        "LOW",
        (progress_factor(29),),
        ("progress",),
        ("REVIEW_STUDY_PLAN",),
    ),
)


SCENARIOS_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}
