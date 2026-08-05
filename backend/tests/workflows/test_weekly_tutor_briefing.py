from __future__ import annotations

from datetime import date

import pytest

from app.workflows.automatic_risk_detection import StudentRiskDetectionResult
from app.workflows.weekly_tutor_briefing import (
    CurrentProgressSnapshot,
    OfflineRecommendationAdapter,
    TutorBriefingAudience,
    TutorBriefingStudentInput,
    WeeklyAcademicEvent,
    WeeklyTutorBriefingGenerator,
    WeeklyTutorBriefingInput,
)


def risk(
    student_id: int,
    *,
    level: str = "HIGH",
    assessment_status: str = "COMPLETE",
    actionable: list[str] | None = None,
    unavailable: list[str] | None = None,
) -> StudentRiskDetectionResult:
    return StudentRiskDetectionResult(
        student_id=student_id,
        risk_level=level,
        risk_score=55,
        assessment_status=assessment_status,
        requires_tutor_attention=True,
        contributing_indicators=["academic_delay", "study_right", "academic_events"],
        unavailable_indicators=unavailable or [],
        score_basis="all_indicators",
        policy_version="academic-risk-v1",
        actionable_indicators=actionable or [],
    )


def progress(*, remaining: int = 0, status: str = "ON_TRACK") -> CurrentProgressSnapshot:
    return CurrentProgressSnapshot(
        completed_ects=60,
        expected_ects=60 + remaining,
        remaining_to_expected_ects=remaining,
        status=status,
    )


def briefing_input(
    *,
    source_status: str = "completed",
    students: list[TutorBriefingStudentInput] | None = None,
) -> WeeklyTutorBriefingInput:
    return WeeklyTutorBriefingInput(
        audience=TutorBriefingAudience(tutor_id=7, display_name="Tutor One"),
        period_start=date(2026, 7, 27),
        period_end=date(2026, 8, 3),
        assigned_student_count=12,
        risk_evaluation_status=source_status,  # type: ignore[arg-type]
        attention_students=students or [],
        academic_events=[WeeklyAcademicEvent("\nCourse deadline\t", "2026-07-30")],
    )


def test_generates_sorted_tutor_scoped_plain_text_with_offline_actions():
    result = WeeklyTutorBriefingGenerator().generate(
        briefing_input(
            students=[
                TutorBriefingStudentInput(
                    student_id=200,
                    display_name="Zoe Student",
                    risk=risk(200, level="HIGH", actionable=["study_right"]),
                    current_progress=progress(),
                ),
                TutorBriefingStudentInput(
                    student_id=100,
                    display_name="Ada\nStudent",
                    risk=risk(
                        100,
                        level="CRITICAL",
                        actionable=["academic_delay", "academic_events"],
                    ),
                    current_progress=progress(remaining=20, status="BEHIND"),
                ),
            ]
        )
    )

    assert result.status == "completed"
    assert [item.student_name for item in result.student_summaries] == [
        "Ada Student",
        "Zoe Student",
    ]
    assert [item.action for item in result.student_summaries[0].recommendations] == [
        "Review the student's study plan.",
        "Schedule a tutor meeting.",
        "Review the upcoming academic deadline with the student and agree on the required next step.",
    ]
    assert result.risk_level_counts == {
        "LOW": 0,
        "MEDIUM": 0,
        "HIGH": 1,
        "CRITICAL": 1,
    }
    assert result.telegram.channel == "telegram"
    assert result.telegram.delivery_status == "NOT_SENT"
    assert "Ada Student" in result.telegram.text
    assert "Course deadline" in result.telegram.text
    assert "100" not in result.telegram.text
    assert "200" not in result.telegram.text
    assert "telegram_chat_id" not in str(result.to_dict())
    assert "student_id" not in str(result.to_dict())


def test_partial_and_missing_information_is_not_presented_as_low_risk():
    result = WeeklyTutorBriefingGenerator().generate(
        briefing_input(
            source_status="partial",
            students=[
                TutorBriefingStudentInput(
                    student_id=100,
                    display_name="Ada Student",
                    risk=risk(
                        100,
                        level="MEDIUM",
                        assessment_status="PARTIAL",
                        actionable=["academic_delay"],
                        unavailable=["tutor_meetings"],
                    ),
                    current_progress=None,
                )
            ],
        )
    )

    assert result.status == "partial"
    assert "Risk evaluation was partial" in result.availability_notes[0]
    assert "Current progress is unavailable." in result.student_summaries[0].availability_notes
    assert "not treated as low risk" in result.telegram.text.lower()
    assert "PARTIAL" not in result.telegram.text
    assert "partial assessment" in result.telegram.text


def test_completed_empty_attention_scope_does_not_claim_a_low_risk_assessment():
    result = WeeklyTutorBriefingGenerator().generate(briefing_input())

    assert result.status == "completed"
    assert result.students_requiring_attention == 0
    assert "No students require confirmed tutor attention." in result.telegram.text
    assert "low risk" not in result.telegram.text.lower()


def test_adapter_never_maps_zero_or_unknown_indicators_to_an_invented_action():
    recommendations, notes = OfflineRecommendationAdapter().recommend(
        risk(100, actionable=["unrecognised_indicator"])
    )

    assert recommendations == []
    assert notes == [
        "No approved offline recommendation mapping is available for 'unrecognised_indicator'."
    ]


def test_rejects_failed_source_with_student_attention_data():
    with pytest.raises(ValueError, match="failed risk evaluation"):
        WeeklyTutorBriefingGenerator().generate(
            briefing_input(
                source_status="failed",
                students=[
                    TutorBriefingStudentInput(
                        student_id=100,
                        display_name="Ada Student",
                        risk=risk(100),
                    )
                ],
            )
        )
