"""Deterministic explanations for existing academic progress results.

This module deliberately does not calculate progress.  It explains the values
already produced by ``ProgressService.get_progress`` and records where each
value came from.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


_PROGRESS_FIELDS = (
    "current_semester",
    "completed_ects",
    "expected_ects",
    "difference_ects",
    "remaining_to_expected_ects",
    "progress_percentage",
    "status",
)

_INDICATOR_ROLES = {
    "current_semester": "Selects the applicable curriculum milestone.",
    "completed_ects": "Reports completed course credits.",
    "expected_ects": "Reports the curriculum milestone for the current semester.",
    "difference_ects": "Reports the existing completed-versus-expected difference.",
    "remaining_to_expected_ects": "Reports the existing credits remaining to the milestone.",
    "progress_percentage": "Reports the existing percentage of expected progress.",
    "status": "Reports the existing progress classification.",
}


@dataclass(frozen=True)
class ProgressExplanationInput:
    """Inputs required to explain an existing progress-service result."""

    student_id: int
    progress_result: dict[str, Any]
    source: str = "get_progress"


@dataclass(frozen=True)
class ProgressIndicator:
    """One source-backed value used in the progress explanation."""

    code: str
    value: Any
    role: str
    source: str


@dataclass(frozen=True)
class ProgressExplanation:
    """Transparent, serialisable explanation of an upstream progress result."""

    student_id: int
    data_status: str
    summary: str
    current_semester: Any = None
    completed_ects: Any = None
    expected_ects: Any = None
    difference_ects: Any = None
    remaining_to_expected_ects: Any = None
    progress_percentage: Any = None
    status: Any = None
    indicators: tuple[ProgressIndicator, ...] = ()
    evidence: tuple[str, ...] = ()
    unavailable_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        return asdict(self)


class ProgressExplanationService:
    """Explain progress values without deriving or changing them."""

    def explain(self, explanation_input: ProgressExplanationInput) -> ProgressExplanation:
        result = explanation_input.progress_result
        source = explanation_input.source

        if not result.get("success") or not isinstance(result.get("progress"), dict):
            warning = str(result.get("error") or "PROGRESS_UNAVAILABLE")
            return ProgressExplanation(
                student_id=explanation_input.student_id,
                data_status="PARTIAL",
                summary="Progress cannot be explained because progress data is unavailable.",
                unavailable_fields=_PROGRESS_FIELDS,
                warnings=(warning,),
            )

        progress = result["progress"]
        unavailable = tuple(
            field_name
            for field_name in _PROGRESS_FIELDS
            if progress.get(field_name) is None
        )
        indicators = tuple(
            ProgressIndicator(
                code=field_name,
                value=progress[field_name],
                role=_INDICATOR_ROLES[field_name],
                source=f"{source}.{field_name}",
            )
            for field_name in _PROGRESS_FIELDS
            if progress.get(field_name) is not None
        )
        evidence = tuple(indicator.source for indicator in indicators)
        data_status = "COMPLETE" if not unavailable else "PARTIAL"
        warnings = (
            ("Some progress fields are unavailable; no missing values were inferred.",)
            if unavailable
            else ()
        )

        return ProgressExplanation(
            student_id=explanation_input.student_id,
            data_status=data_status,
            summary=self._summary(progress, unavailable),
            current_semester=progress.get("current_semester"),
            completed_ects=progress.get("completed_ects"),
            expected_ects=progress.get("expected_ects"),
            difference_ects=progress.get("difference_ects"),
            remaining_to_expected_ects=progress.get("remaining_to_expected_ects"),
            progress_percentage=progress.get("progress_percentage"),
            status=progress.get("status"),
            indicators=indicators,
            evidence=evidence,
            unavailable_fields=unavailable,
            warnings=warnings,
        )

    @staticmethod
    def _summary(progress: dict[str, Any], unavailable: tuple[str, ...]) -> str:
        if unavailable:
            return (
                "Progress is only partially explainable because required values "
                "are unavailable."
            )

        return (
            f"Progress status is {progress['status']}: {progress['completed_ects']} ECTS "
            f"completed against {progress['expected_ects']} ECTS expected for semester "
            f"{progress['current_semester']}. The reported difference is "
            f"{progress['difference_ects']} ECTS and reported progress is "
            f"{progress['progress_percentage']}%."
        )
