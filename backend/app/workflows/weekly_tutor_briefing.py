"""Deterministic previous-week tutor briefing composition for Issue #105.

This module intentionally has no scheduler, database, Telegram, RAG, or LLM
dependency.  Issue #103 supplies the reporting period, Issue #104 supplies
canonical risk evidence, and the caller supplies a tutor-scoped input assembled
from already-authoritative results.  Issue #101 remains responsible for the
separate upcoming-week Monday briefing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from app.workflows.automatic_risk_detection import (
    CANONICAL_RISK_LEVELS,
    StudentRiskDetectionResult,
)


WEEKLY_TUTOR_BRIEFING_NAME = "weekly_tutor_briefing"
BRIEFING_SCHEMA_VERSION = 1

BriefingStatus = Literal["completed", "partial", "failed"]
SourceStatus = Literal["completed", "partial", "failed"]

_ATTENTION_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
_ACTION_MAPPINGS = {
    "academic_delay": (
        "progress",
        "Review the student's study plan.",
    ),
    "study_right": (
        "study_right",
        "Check study-right extension/support options.",
    ),
    "academic_events": (
        "deadline",
        "Review the upcoming academic deadline with the student and agree on the required next step.",
    ),
}


@dataclass(frozen=True)
class TutorBriefingAudience:
    """An authorised tutor scope.  Delivery identifiers are intentionally absent."""

    tutor_id: int
    display_name: str


@dataclass(frozen=True)
class CurrentProgressSnapshot:
    """A current-state #91 progress view; it is not a weekly ECTS delta."""

    completed_ects: int
    expected_ects: int
    remaining_to_expected_ects: int
    status: str


@dataclass(frozen=True)
class WeeklyAcademicEvent:
    """A presentation-safe event already filtered to the reporting period."""

    event_name: str
    event_date: str


@dataclass(frozen=True)
class TutorBriefingStudentInput:
    """One assigned student with an already-computed canonical attention result."""

    student_id: int
    display_name: str
    risk: StudentRiskDetectionResult
    current_progress: CurrentProgressSnapshot | None = None


@dataclass(frozen=True)
class WeeklyTutorBriefingInput:
    """Typed, tutor-scoped input assembled without recalculating analytics."""

    audience: TutorBriefingAudience
    period_start: date
    period_end: date
    assigned_student_count: int
    risk_evaluation_status: SourceStatus
    attention_students: list[TutorBriefingStudentInput] = field(default_factory=list)
    academic_events: list[WeeklyAcademicEvent] = field(default_factory=list)


@dataclass(frozen=True)
class TutorActionRecommendation:
    """A deterministic, offline advisory action mapped from canonical evidence."""

    priority: str
    category: str
    action: str
    source_indicator: str
    policy_context_used: bool = False


@dataclass(frozen=True)
class TutorBriefingStudentSummary:
    """Presentation-safe summary; stable internal student identifiers are omitted."""

    student_name: str
    risk_level: str
    assessment_status: str
    requires_tutor_attention: bool
    current_progress: CurrentProgressSnapshot | None
    recommendations: list[TutorActionRecommendation]
    unavailable_indicators: list[str]
    availability_notes: list[str]


@dataclass(frozen=True)
class TelegramReadyBriefing:
    """Unsent plain-text handoff for Issue #107, without destination details."""

    channel: Literal["telegram"]
    delivery_status: Literal["NOT_SENT"]
    text: str


@dataclass(frozen=True)
class WeeklyTutorBriefing:
    """Serializable #105 result for one tutor and one completed weekly period."""

    workflow_name: str
    schema_version: int
    tutor_name: str
    period_start: str
    period_end: str
    status: BriefingStatus
    assigned_student_count: int
    students_requiring_attention: int
    risk_level_counts: dict[str, int]
    student_summaries: list[TutorBriefingStudentSummary]
    academic_events: list[WeeklyAcademicEvent]
    availability_notes: list[str]
    warnings: list[str]
    errors: list[str]
    telegram: TelegramReadyBriefing

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OfflineRecommendationAdapter:
    """Map verified canonical indicators to the existing advisory action wording.

    The adapter never performs policy retrieval.  It maps only non-zero
    ``actionable_indicators`` emitted by #104, so a present-but-zero indicator
    cannot create a recommendation.
    """

    def recommend(
        self,
        risk: StudentRiskDetectionResult,
    ) -> tuple[list[TutorActionRecommendation], list[str]]:
        recommendations: list[TutorActionRecommendation] = []
        notes: list[str] = []
        actionable = list(dict.fromkeys(risk.actionable_indicators))

        for indicator in actionable:
            mapping = _ACTION_MAPPINGS.get(indicator)
            if mapping is None:
                notes.append(
                    f"No approved offline recommendation mapping is available for '{indicator}'."
                )
                continue
            category, action = mapping
            recommendations.append(
                TutorActionRecommendation(
                    priority=risk.risk_level,
                    category=category,
                    action=action,
                    source_indicator=indicator,
                )
            )
            if indicator == "academic_delay" and risk.requires_tutor_attention:
                recommendations.append(
                    TutorActionRecommendation(
                        priority=risk.risk_level,
                        category="progress",
                        action="Schedule a tutor meeting.",
                        source_indicator=indicator,
                    )
                )

        if not actionable:
            notes.append("No verified actionable risk indicator was supplied.")
        return recommendations, notes


class WeeklyTutorBriefingGenerator:
    """Compose a concise, deterministic briefing from supplied typed results."""

    def __init__(self, recommendation_adapter: OfflineRecommendationAdapter | None = None) -> None:
        self._recommendation_adapter = recommendation_adapter or OfflineRecommendationAdapter()

    def generate(self, briefing_input: WeeklyTutorBriefingInput) -> WeeklyTutorBriefing:
        _validate_input(briefing_input)
        summaries: list[TutorBriefingStudentSummary] = []
        notes: list[str] = []

        for student in sorted(briefing_input.attention_students, key=_student_sort_key):
            recommendations, recommendation_notes = self._recommendation_adapter.recommend(
                student.risk
            )
            student_notes = list(recommendation_notes)
            if student.risk.assessment_status == "PARTIAL":
                student_notes.append("Risk assessment is partial.")
            if student.risk.unavailable_indicators:
                student_notes.append(
                    "Unavailable risk indicators: "
                    + ", ".join(student.risk.unavailable_indicators)
                    + "."
                )
            if student.current_progress is None:
                student_notes.append("Current progress is unavailable.")

            summaries.append(
                TutorBriefingStudentSummary(
                    student_name=_single_line(student.display_name),
                    risk_level=student.risk.risk_level,
                    assessment_status=student.risk.assessment_status,
                    requires_tutor_attention=student.risk.requires_tutor_attention,
                    current_progress=student.current_progress,
                    recommendations=recommendations,
                    unavailable_indicators=list(student.risk.unavailable_indicators),
                    availability_notes=student_notes,
                )
            )

        if briefing_input.risk_evaluation_status == "partial":
            notes.append("Risk evaluation was partial; unavailable results are not treated as low risk.")
        elif briefing_input.risk_evaluation_status == "failed":
            notes.append("Risk evaluation was unavailable for this briefing scope.")

        for summary in summaries:
            notes.extend(summary.availability_notes)
        notes = _deduplicate(notes)
        status = _status_for(briefing_input, summaries)
        counts = _risk_level_counts(summaries)
        errors = ["RISK_EVALUATION_UNAVAILABLE"] if status == "failed" else []
        telegram = TelegramReadyBriefing(
            channel="telegram",
            delivery_status="NOT_SENT",
            text=_render_telegram_text(
                briefing_input=briefing_input,
                summaries=summaries,
                availability_notes=notes,
            ),
        )

        return WeeklyTutorBriefing(
            workflow_name=WEEKLY_TUTOR_BRIEFING_NAME,
            schema_version=BRIEFING_SCHEMA_VERSION,
            tutor_name=_single_line(briefing_input.audience.display_name),
            period_start=briefing_input.period_start.isoformat(),
            period_end=briefing_input.period_end.isoformat(),
            status=status,
            assigned_student_count=briefing_input.assigned_student_count,
            students_requiring_attention=len(summaries),
            risk_level_counts=counts,
            student_summaries=summaries,
            academic_events=sorted(
                briefing_input.academic_events,
                key=lambda event: (event.event_date, _single_line(event.event_name).casefold()),
            ),
            availability_notes=notes,
            warnings=notes if status == "partial" else [],
            errors=errors,
            telegram=telegram,
        )


def generate_weekly_tutor_briefing(
    briefing_input: WeeklyTutorBriefingInput,
) -> WeeklyTutorBriefing:
    """Convenience entry point for deterministic, dependency-free composition."""

    return WeeklyTutorBriefingGenerator().generate(briefing_input)


def _validate_input(briefing_input: WeeklyTutorBriefingInput) -> None:
    if not isinstance(briefing_input.audience.tutor_id, int) or briefing_input.audience.tutor_id <= 0:
        raise ValueError("audience.tutor_id must be a positive integer")
    if not _single_line(briefing_input.audience.display_name):
        raise ValueError("audience.display_name must not be empty")
    if briefing_input.period_start >= briefing_input.period_end:
        raise ValueError("period_start must be earlier than period_end")
    if briefing_input.risk_evaluation_status not in {"completed", "partial", "failed"}:
        raise ValueError("risk_evaluation_status is invalid")
    if (
        not isinstance(briefing_input.assigned_student_count, int)
        or isinstance(briefing_input.assigned_student_count, bool)
        or briefing_input.assigned_student_count < len(briefing_input.attention_students)
    ):
        raise ValueError("assigned_student_count cannot be smaller than attention_students")
    if briefing_input.risk_evaluation_status == "failed" and briefing_input.attention_students:
        raise ValueError("failed risk evaluation cannot contain attention students")

    student_ids: set[int] = set()
    for student in briefing_input.attention_students:
        if not isinstance(student.student_id, int) or student.student_id <= 0:
            raise ValueError("student_id must be a positive integer")
        if student.student_id in student_ids:
            raise ValueError("attention_students must not contain duplicate student IDs")
        student_ids.add(student.student_id)
        if not _single_line(student.display_name):
            raise ValueError("student display_name must not be empty")
        if student.risk.student_id != student.student_id:
            raise ValueError("student risk result does not match the scoped student")
        if student.risk.risk_level not in CANONICAL_RISK_LEVELS:
            raise ValueError("student risk result has a non-canonical risk level")
        if (
            not student.risk.requires_tutor_attention
            or student.risk.risk_level not in _ATTENTION_ORDER
        ):
            raise ValueError("attention_students must require tutor attention")


def _status_for(
    briefing_input: WeeklyTutorBriefingInput,
    summaries: list[TutorBriefingStudentSummary],
) -> BriefingStatus:
    if briefing_input.risk_evaluation_status == "failed":
        return "failed"
    if briefing_input.risk_evaluation_status == "partial":
        return "partial"
    if any(
        summary.assessment_status == "PARTIAL"
        or summary.current_progress is None
        or summary.availability_notes
        for summary in summaries
    ):
        return "partial"
    return "completed"


def _risk_level_counts(
    summaries: list[TutorBriefingStudentSummary],
) -> dict[str, int]:
    counts = {level: 0 for level in CANONICAL_RISK_LEVELS}
    for summary in summaries:
        counts[summary.risk_level] += 1
    return counts


def _student_sort_key(student: TutorBriefingStudentInput) -> tuple[int, str, int]:
    return (
        _ATTENTION_ORDER.get(student.risk.risk_level, len(_ATTENTION_ORDER)),
        _single_line(student.display_name).casefold(),
        student.student_id,
    )


def _render_telegram_text(
    *,
    briefing_input: WeeklyTutorBriefingInput,
    summaries: list[TutorBriefingStudentSummary],
    availability_notes: list[str],
) -> str:
    lines = [
        f"Weekly tutor briefing for {_single_line(briefing_input.audience.display_name)}",
        (
            "Reporting period (previous completed week): "
            f"{briefing_input.period_start.isoformat()} to {briefing_input.period_end.isoformat()}"
        ),
        f"Assigned students: {briefing_input.assigned_student_count}",
        f"Students requiring tutor attention: {len(summaries)}",
    ]

    if summaries:
        lines.extend(["", "Students requiring attention"])
        for summary in summaries:
            details = [f"{summary.risk_level} risk ({summary.assessment_status.lower()} assessment)"]
            if summary.current_progress is not None:
                remaining = summary.current_progress.remaining_to_expected_ects
                if remaining > 0:
                    details.append(f"{remaining} ECTS below expected")
                else:
                    details.append(f"progress: {summary.current_progress.status.lower()}")
            else:
                details.append("current progress unavailable")
            lines.append(f"- {summary.student_name}: {'; '.join(details)}")
            if summary.recommendations:
                lines.append(
                    "  Actions: "
                    + "; ".join(item.action for item in summary.recommendations)
                )
    elif briefing_input.risk_evaluation_status == "completed":
        lines.extend(["", "No students require confirmed tutor attention."])
    else:
        lines.extend(["", "No confirmed attention result is available for this scope."])

    if briefing_input.academic_events:
        lines.extend(["", "Academic events in this reporting period"])
        for event in sorted(
            briefing_input.academic_events,
            key=lambda value: (value.event_date, _single_line(value.event_name).casefold()),
        ):
            lines.append(f"- {_single_line(event.event_date)}: {_single_line(event.event_name)}")

    if availability_notes:
        lines.extend(["", "Availability notes"])
        lines.extend(f"- {_single_line(note)}" for note in availability_notes)
    return "\n".join(lines)


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
