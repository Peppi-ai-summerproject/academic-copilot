"""HTTP contract tests for the Issue #97 progress dashboard endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_student_dashboard_service
from app.api.routes.progress import router


class FakeDashboardService:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[int, date | None]] = []

    def get_student_dashboard(
        self,
        student_id: int,
        *,
        as_of_date: date | None = None,
    ):
        self.calls.append((student_id, as_of_date))
        if self.error is not None:
            raise self.error
        return self.response


def dashboard_response(
    *,
    risk_level="LOW",
    risk_score=0,
    health_score=100,
    health_level="STRONG",
    assessment_status="COMPLETE",
    priority="LOW",
    attention_required=False,
    risk_source="ACADEMIC_RISK_SCORING_SERVICE",
):
    return {
        "success": True,
        "student_id": 1,
        "dashboard": {
            "profile": {"student_id": 1, "programme": "Business IT"},
            "academic_progress": {
                "available": True,
                "completed_ects": 90,
                "expected_ects": 120,
                "difference_ects": -30,
                "remaining_to_expected_ects": 30,
                "progress_percentage": 75.0,
                "status": "BEHIND",
            },
            "study_right": {"available": True, "status": "ACTIVE"},
            "academic_health": {
                "success": health_score is not None,
                "assessment_status": assessment_status,
                "health_score": health_score,
                "health_level": health_level,
            },
            "risk": {
                "current_analysis": {
                    "risk_level": risk_level,
                    "score": risk_score,
                    "assessment_status": assessment_status,
                    "source": risk_source,
                },
                "supporting_legacy_analysis": {
                    "authoritative_overall_risk": False,
                    "risk_level": "LOW",
                },
                "events": [],
            },
            "upcoming_actions": {
                "academic_events": [],
                "tutor_meetings": [],
                "recommended_actions": [],
            },
            "summary": {
                "overall_status": "NEEDS_ATTENTION" if attention_required else "ON_TRACK",
                "attention_required": attention_required,
                "priority": priority,
                "key_findings": ["Canonical dashboard result."],
            },
        },
    }


def client_for(service: FakeDashboardService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/students")
    app.dependency_overrides[get_student_dashboard_service] = lambda: service
    return TestClient(app)


def test_endpoint_is_registered_and_returns_dashboard_progress_metrics():
    service = FakeDashboardService(dashboard_response())
    client = client_for(service)

    response = client.get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    progress = body["dashboard"]["academic_progress"]
    assert progress["completed_ects"] == 90
    assert progress["expected_ects"] == 120
    assert progress["difference_ects"] == -30
    assert progress["status"] == "BEHIND"
    assert service.calls == [(1, None)]
    assert "/api/v1/students/{student_id}/progress-dashboard" in client.get(
        "/openapi.json"
    ).json()["paths"]


@pytest.mark.parametrize(
    ("risk_level", "risk_score", "health_score", "health_level", "priority", "attention"),
    [
        ("LOW", 0, 100, "STRONG", "LOW", False),
        ("MEDIUM", 20, 80, "STABLE", "MEDIUM", True),
        ("HIGH", 40, 60, "NEEDS_ATTENTION", "HIGH", True),
        ("CRITICAL", 70, 30, "URGENT_SUPPORT", "HIGH", True),
    ],
)
def test_endpoint_preserves_canonical_risk_health_and_summary(
    risk_level,
    risk_score,
    health_score,
    health_level,
    priority,
    attention,
):
    service = FakeDashboardService(dashboard_response(
        risk_level=risk_level,
        risk_score=risk_score,
        health_score=health_score,
        health_level=health_level,
        priority=priority,
        attention_required=attention,
    ))

    response = client_for(service).get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 200
    dashboard = response.json()["dashboard"]
    current_risk = dashboard["risk"]["current_analysis"]
    health = dashboard["academic_health"]
    assert (current_risk["risk_level"], current_risk["score"]) == (
        risk_level,
        risk_score,
    )
    assert (health["health_score"], health["health_level"]) == (
        health_score,
        health_level,
    )
    assert dashboard["summary"]["priority"] == priority
    assert dashboard["summary"]["attention_required"] is attention
    assert dashboard["risk"]["supporting_legacy_analysis"][
        "authoritative_overall_risk"
    ] is False


def test_endpoint_preserves_partial_risk_without_downgrading_it_to_low():
    service = FakeDashboardService(dashboard_response(
        risk_level=None,
        risk_score=None,
        health_score=None,
        health_level=None,
        assessment_status="PARTIAL",
        priority="UNKNOWN",
        attention_required=True,
    ))

    response = client_for(service).get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 200
    dashboard = response.json()["dashboard"]
    assert dashboard["risk"]["current_analysis"]["risk_level"] is None
    assert dashboard["academic_health"]["health_score"] is None
    assert dashboard["summary"]["priority"] == "UNKNOWN"
    assert dashboard["summary"]["attention_required"] is True


def test_endpoint_preserves_unavailable_canonical_fallback():
    service = FakeDashboardService(dashboard_response(
        risk_level=None,
        risk_score=None,
        health_score=None,
        health_level=None,
        assessment_status="UNAVAILABLE",
        priority="UNKNOWN",
        attention_required=True,
        risk_source="LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK",
    ))

    response = client_for(service).get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 200
    dashboard = response.json()["dashboard"]
    current = dashboard["risk"]["current_analysis"]
    assert current["source"] == "LEGACY_PROGRESS_STUDY_RIGHT_FALLBACK"
    assert current["risk_level"] is None
    assert dashboard["summary"]["priority"] == "UNKNOWN"


def test_endpoint_forwards_one_explicit_effective_date_to_dashboard_service():
    service = FakeDashboardService(dashboard_response())

    response = client_for(service).get(
        "/api/v1/students/1/progress-dashboard?as_of_date=2026-08-08"
    )

    assert response.status_code == 200
    assert service.calls == [(1, date(2026, 8, 8))]


def test_unknown_student_returns_a_safe_not_found_response():
    service = FakeDashboardService({
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 404 was not found.",
    })

    response = client_for(service).get("/api/v1/students/404/progress-dashboard")

    assert response.status_code == 404
    assert response.json() == {"detail": "Student with ID 404 was not found."}
    assert service.calls == [(404, None)]


def test_invalid_student_id_is_rejected_before_service_invocation():
    service = FakeDashboardService(dashboard_response())

    response = client_for(service).get("/api/v1/students/0/progress-dashboard")

    assert response.status_code == 422
    assert service.calls == []


def test_malformed_effective_date_is_rejected_before_service_invocation():
    service = FakeDashboardService(dashboard_response())

    response = client_for(service).get(
        "/api/v1/students/1/progress-dashboard?as_of_date=not-a-date"
    )

    assert response.status_code == 422
    assert service.calls == []


def test_internal_service_failure_has_no_internal_error_detail():
    service = FakeDashboardService(error=RuntimeError("database host details"))

    response = client_for(service).get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to retrieve the progress dashboard."}
    assert "database host details" not in response.text


def test_returned_internal_failure_has_the_same_safe_error_response():
    service = FakeDashboardService({
        "success": False,
        "error": "DATABASE_ERROR",
        "message": "Database connection details must not be exposed.",
    })

    response = client_for(service).get("/api/v1/students/1/progress-dashboard")

    assert response.status_code == 500
    assert response.json() == {"detail": "Unable to retrieve the progress dashboard."}
    assert "connection details" not in response.text


def test_application_router_registers_the_progress_dashboard_when_optional_agents_are_available():
    pytest.importorskip("langgraph")
    pytest.importorskip("qdrant_client")
    from app.api.api_router import api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")

    assert "/api/v1/students/{student_id}/progress-dashboard" in TestClient(app).get(
        "/openapi.json"
    ).json()["paths"]
