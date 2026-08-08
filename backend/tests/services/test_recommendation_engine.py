from app.services.recommendation_engine import (
    RecommendationEngine,
    RecommendationInput,
    SupportingEvidence,
)


def recommendation_input(
    *factors: dict,
    complete: bool = True,
    unavailable: tuple[str, ...] = (),
) -> RecommendationInput:
    return RecommendationInput(
        student_id=42,
        risk_level="HIGH",
        risk_factors=factors,
        assessment_status="COMPLETE" if complete else "PARTIAL",
        unavailable_dimensions=unavailable,
        supporting_evidence={
            "progress": SupportingEvidence("progress", {"completed_ects": 60}),
        },
    )


def factor(dimension: str, level: str = "HIGH", **values) -> dict:
    return {
        "dimension": dimension,
        "level": level,
        "reason": f"Confirmed {dimension} concern.",
        "values": values,
        "evidence_source": "risk",
    }


def test_engine_maps_evidence_without_recalculating_academic_facts():
    result = RecommendationEngine().evaluate(
        recommendation_input(factor("progress", ects_deficit=70))
    )

    assert [decision.action for decision in result.decisions] == [
        "Review the student's study plan.",
        "Schedule a tutor meeting.",
    ]
    assert result.decisions[0].reason_codes == ("PROGRESS_REVIEW_STUDY_PLAN",)
    assert result.decisions[0].evidence[0].values == {"ects_deficit": 70}
    assert result.decisions[0].source_agents == ("risk", "progress")
    assert result.complete


def test_low_progress_priority_does_not_trigger_meeting_rule():
    result = RecommendationEngine().evaluate(
        recommendation_input(factor("progress", "LOW", ects_deficit=5))
    )

    assert [decision.reason_codes for decision in result.decisions] == [
        ("PROGRESS_REVIEW_STUDY_PLAN",),
    ]


def test_partial_input_preserves_unavailable_dimensions_and_provenance():
    result = RecommendationEngine().evaluate(
        recommendation_input(
            factor("study_right", "MEDIUM", status="EXPIRES_SOON"),
            complete=False,
            unavailable=("tutor_meetings",),
        )
    )

    assert result.data_status == "PARTIAL"
    assert result.unavailable_dimensions == ("tutor_meetings",)
    assert not result.complete
    assert result.decisions[0].evidence[0].source == "risk"


def test_unknown_factor_is_not_invented_and_marks_assessment_incomplete():
    result = RecommendationEngine().evaluate(
        recommendation_input(factor("unsupported_dimension"))
    )

    assert result.decisions == ()
    assert result.missing_information == (
        "No approved recommendation mapping for risk factor "
        "'unsupported_dimension'.",
    )
    assert not result.complete


def test_no_risk_is_a_complete_empty_decision_set():
    value = RecommendationInput(
        student_id=42,
        risk_level="NONE",
        risk_factors=(),
        assessment_status="COMPLETE",
    )

    result = RecommendationEngine().evaluate(value)

    assert result.complete
    assert result.decisions == ()
