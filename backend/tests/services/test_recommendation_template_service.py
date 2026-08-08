"""Tests for recommendation presentation templates — Issue #115."""

from app.services.recommendation_template_service import (
    RecommendationTemplateInput,
    RecommendationTemplateService,
    ScenarioTemplate,
)


def recommendation(kind: str = "progress", **overrides):
    value = {
        "recommendation_type": kind,
        "priority": "HIGH",
        "action": "Review the student's study plan.",
        "explanation": "Verified student fact: progress is behind.",
        "student_evidence": [
            {
                "source_agent": "risk",
                "reason": "Confirmed progress concern.",
                "values": {"ects_deficit": 30},
            }
        ],
        "policy_evidence": [],
    }
    value.update(overrides)
    return value


def render(*recommendations, **overrides):
    values = {
        "student_id": 42,
        "data_status": "COMPLETE",
        "recommendations": tuple(recommendations),
    }
    values.update(overrides)
    return RecommendationTemplateService().render(RecommendationTemplateInput(**values))


def test_normal_progress_uses_monitoring_template_without_warning_language():
    output = render(
        recommendation(
            "monitoring",
            priority="LOW",
            action="Continue normal progress monitoring.",
            explanation="No confirmed risk factors were found.",
            student_evidence=[],
        )
    )
    assert "Normal academic monitoring" in output.text
    assert "Continue normal progress monitoring." in output.text
    assert "Data availability" not in output.text


def test_delayed_student_preserves_progress_evidence():
    output = render(recommendation())
    assert "Academic progress support" in output.text
    assert "ects_deficit=30" in output.text
    assert "HIGH" in output.text


def test_high_risk_explanation_is_preserved_when_supplied():
    output = render(
        recommendation(),
        risk_explanation={
            "summary": "The student is classified as HIGH risk with score 72/100.",
            "warnings": [],
        },
    )
    assert "Risk explanation" in output.text
    assert "HIGH risk with score 72/100" in output.text


def test_study_right_scenario_and_progress_explanation_are_supported():
    output = render(
        recommendation("study_right", action="Review study-right support options."),
        progress_explanation={"summary": "Progress status is BEHIND.", "warnings": []},
    )
    assert "Study-right support" in output.text
    assert "Progress explanation" in output.text


def test_multiple_interventions_preserve_order_without_introducing_duplicates():
    interventions = (
        {"priority": "HIGH", "action": "Schedule a tutor meeting."},
        {"priority": "MEDIUM", "action": "Review the study plan."},
    )
    output = render(recommendation(), interventions=interventions)
    first = output.text.index("Schedule a tutor meeting")
    second = output.text.index("Review the study plan")
    assert first < second
    assert output.text.count("Review the study plan") == 1


def test_policy_section_is_optional_and_never_fabricated():
    absent = render(recommendation())
    present = render(
        recommendation(
            policy_evidence=[
                {"source": "Academic Policy", "excerpt": "Tutors provide guidance."}
            ]
        )
    )
    assert "Relevant guidance" not in absent.text
    assert "Academic Policy: Tutors provide guidance." in present.text


def test_partial_data_is_visible_and_missing_optional_sections_are_clean():
    output = render(
        data_status="PARTIAL",
        missing_information=("Policy evidence unavailable.",),
        unavailable_dimensions=("academic_events",),
    )
    assert "Status: PARTIAL" in output.text
    assert "Policy evidence unavailable." in output.text
    assert "Unavailable: academic_events" in output.text
    assert "Supporting evidence" not in output.text
    assert "Relevant guidance" not in output.text


def test_rendering_is_deterministic_and_scenarios_are_extensible():
    value = RecommendationTemplateInput(
        student_id=42,
        data_status="COMPLETE",
        recommendations=(recommendation("custom"),),
    )
    service = RecommendationTemplateService(
        {"custom": ScenarioTemplate("Custom support", "Custom situation")}
    )
    assert service.render(value) == service.render(value)
    assert "Custom support" in service.render(value).text
