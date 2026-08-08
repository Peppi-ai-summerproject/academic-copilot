from app.services.intervention_suggestion_service import (
    InterventionInput,
    InterventionSuggestionService,
)
from app.services.recommendation_engine import (
    RecommendationDecision,
    RecommendationEvidence,
)


def decision(
    reason_code: str,
    *,
    priority: str = "MEDIUM",
    action: str = "Take an approved action.",
    values: dict | None = None,
) -> RecommendationDecision:
    evidence = RecommendationEvidence(
        source="risk",
        reason="Verified academic situation.",
        values=values or {},
    )
    return RecommendationDecision(
        recommendation_type="test",
        priority=priority,
        action=action,
        reason_codes=(reason_code,),
        evidence=(evidence,),
        source_agents=("risk",),
        policy_query=f"policy for {reason_code}",
    )


def intervention_input(
    *decisions: RecommendationDecision,
    complete: bool = True,
    unavailable: tuple[str, ...] = (),
) -> InterventionInput:
    return InterventionInput(
        student_id=42,
        data_status="COMPLETE" if complete else "PARTIAL",
        recommendation_decisions=decisions,
        unavailable_dimensions=unavailable,
    )


def test_healthy_recommendation_becomes_low_priority_monitoring_action():
    result = InterventionSuggestionService().suggest(
        intervention_input(
            decision(
                "NO_CONFIRMED_RISK_CONTINUE_MONITORING",
                priority="LOW",
                action="Continue normal progress monitoring.",
            )
        )
    )

    assert result.complete
    assert len(result.suggestions) == 1
    suggestion = result.suggestions[0]
    assert suggestion.intervention_type == "MONITOR_PROGRESS"
    assert suggestion.priority == "LOW"
    assert suggestion.action == "Continue normal progress monitoring."


def test_progress_rules_produce_context_aware_study_plan_and_meeting_actions():
    result = InterventionSuggestionService().suggest(
        intervention_input(
            decision(
                "PROGRESS_REVIEW_STUDY_PLAN",
                priority="MEDIUM",
                action="Review the student's study plan.",
                values={"ects_deficit": 35},
            ),
            decision(
                "PROGRESS_SCHEDULE_TUTOR_MEETING",
                priority="HIGH",
                action="Schedule a tutor meeting.",
                values={"ects_deficit": 65},
            ),
        )
    )

    assert [item.intervention_type for item in result.suggestions] == [
        "SCHEDULE_TUTOR_MEETING",
        "REVIEW_STUDY_PLAN",
    ]
    assert result.suggestions[0].priority == "HIGH"
    assert result.suggestions[1].evidence[0].values == {"ects_deficit": 35}


def test_study_right_and_deadline_recommendations_keep_specific_actions():
    result = InterventionSuggestionService().suggest(
        intervention_input(
            decision(
                "STUDY_RIGHT_REVIEW_SUPPORT_OPTIONS",
                action="Review study-right support options.",
            ),
            decision(
                "ACADEMIC_DEADLINE_REVIEW_NEXT_STEP",
                action="Review the upcoming deadline.",
            ),
        )
    )

    assert {item.intervention_type for item in result.suggestions} == {
        "REVIEW_STUDY_RIGHT",
        "REVIEW_ACADEMIC_DEADLINE",
    }


def test_duplicate_intervention_is_collapsed_and_keeps_highest_priority():
    first = decision(
        "PROGRESS_REVIEW_STUDY_PLAN",
        priority="LOW",
        action="Review the student's study plan.",
        values={"ects_deficit": 10},
    )
    second = decision(
        "PROGRESS_REVIEW_STUDY_PLAN",
        priority="HIGH",
        action="Review the student's study plan.",
        values={"ects_deficit": 70},
    )

    result = InterventionSuggestionService().suggest(
        intervention_input(first, second)
    )

    assert len(result.suggestions) == 1
    suggestion = result.suggestions[0]
    assert suggestion.priority == "HIGH"
    assert [item.values for item in suggestion.evidence] == [
        {"ects_deficit": 10},
        {"ects_deficit": 70},
    ]


def test_partial_data_and_unavailable_meetings_are_preserved_not_inferred():
    result = InterventionSuggestionService().suggest(
        intervention_input(
            decision(
                "PROGRESS_REVIEW_STUDY_PLAN",
                action="Review the student's study plan.",
            ),
            complete=False,
            unavailable=("tutor_meetings",),
        )
    )

    assert result.data_status == "PARTIAL"
    assert result.unavailable_dimensions == ("tutor_meetings",)
    assert not result.complete
    assert [item.intervention_type for item in result.suggestions] == [
        "REVIEW_STUDY_PLAN"
    ]
    assert all(
        item.intervention_type != "SCHEDULE_TUTOR_MEETING"
        for item in result.suggestions
    )


def test_unknown_reason_does_not_invent_an_intervention():
    result = InterventionSuggestionService().suggest(
        intervention_input(decision("UNSUPPORTED_RECOMMENDATION_REASON"))
    )

    assert result.suggestions == ()
    assert result.missing_information == (
        "No approved intervention mapping for recommendation reason "
        "'UNSUPPORTED_RECOMMENDATION_REASON'.",
    )
    assert not result.complete


def test_same_input_produces_same_ordered_result():
    value = intervention_input(
        decision("PROGRESS_REVIEW_STUDY_PLAN", priority="MEDIUM"),
        decision("STUDY_RIGHT_REVIEW_SUPPORT_OPTIONS", priority="HIGH"),
        decision("ACADEMIC_DEADLINE_REVIEW_NEXT_STEP", priority="MEDIUM"),
    )
    service = InterventionSuggestionService()

    first = service.suggest(value)
    second = service.suggest(value)

    assert first == second
    assert [item.intervention_type for item in first.suggestions] == [
        "REVIEW_STUDY_RIGHT",
        "REVIEW_STUDY_PLAN",
        "REVIEW_ACADEMIC_DEADLINE",
    ]
