"""HTTP API for the existing student progress dashboard contract."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from app.api.dependencies import StudentDashboardServiceDep


router = APIRouter()


@router.get(
    "/{student_id}/progress-dashboard",
    summary="Get the canonical academic progress dashboard for one student",
    response_description="Existing StudentDashboardService response",
)
def get_progress_dashboard(
    student_id: Annotated[
        int,
        Path(gt=0, description="Canonical numeric student ID."),
    ],
    dashboard_service: StudentDashboardServiceDep,
    as_of_date: date | None = Query(
        default=None,
        description="Optional ISO-8601 effective date for date-sensitive analytics.",
    ),
) -> dict[str, Any]:
    """Expose existing dashboard analytics without recalculating them in HTTP."""

    try:
        result = dashboard_service.get_student_dashboard(
            student_id,
            as_of_date=as_of_date,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve the progress dashboard.",
        ) from exc

    if result.get("success"):
        return result

    if result.get("error") == "STUDENT_NOT_FOUND":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result.get("message", "Student was not found."),
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Unable to retrieve the progress dashboard.",
    )
