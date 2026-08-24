from datetime import date

from app.services.available_evidence_risk_service import AvailableEvidenceRiskService


class Provider:
    def __init__(self, result):
        self.result = result

    def get_progress(self, _student_id):
        return self.result

    def get_study_right(self, _student_id):
        return self.result

    def get_upcoming_events(self, **_kwargs):
        return self.result

    def evaluate_student(self, _student_id, **_kwargs):
        return self.result


def test_verified_progress_survives_unavailable_optional_dimensions():
    progress = Provider({
        "success": True,
        "progress": {
            "status": "BEHIND",
            "completed_ects": 0,
            "expected_ects": 30,
            "difference_ects": -30,
        },
    })
    unavailable = Provider({"success": False, "error": "UNAVAILABLE"})
    service = AvailableEvidenceRiskService(
        progress_provider=progress,
        study_right_provider=unavailable,
        event_provider=unavailable,
        tutor_meeting_provider=unavailable,
    )

    result = service.assess_student_risk(102, as_of_date=date(2026, 8, 24))

    assert result["success"] is True
    assert result["assessment_status"] == "PARTIAL"
    assert result["risk_level"] == "MEDIUM"
    assert result["risk_factors"][0]["values"]["ects_deficit"] == 30
    assert result["unavailable_dimensions"] == [
        "study_right", "academic_events", "tutor_meetings"
    ]
