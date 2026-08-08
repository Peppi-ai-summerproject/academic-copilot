from collections.abc import Generator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.repositories.event_repository import EventRepository
from app.repositories.progress_repository import ProgressRepository
from app.repositories.student_repository import StudentRepository
from app.repositories.study_right_repository import StudyRightRepository
from app.repositories.tutor_meeting_repository import TutorMeetingRepository
from app.services.academic_health_score_service import AcademicHealthScoreService
from app.services.academic_risk_scoring_service import AcademicRiskScoringService
from app.services.delay_detection_service import DelayDetectionService
from app.services.event_service import EventService
from app.services.health_service import HealthService
from app.services.progress_service import ProgressService
from app.services.student_dashboard_service import StudentDashboardService
from app.services.student_service import StudentService
from app.services.study_right_risk_service import StudyRightRiskService
from app.services.study_right_service import StudyRightService
from app.services.tutor_meeting_risk_service import TutorMeetingRiskService


def get_db_session() -> Generator[Session, None, None]:
    database_session = SessionLocal()

    try:
        yield database_session
    finally:
        database_session.close()


DatabaseSessionDep = Annotated[
    Session,
    Depends(get_db_session),
]


def get_health_service() -> HealthService:
    return HealthService()


HealthServiceDep = Annotated[
    HealthService,
    Depends(get_health_service),
]


def get_student_dashboard_service(
    database_session: DatabaseSessionDep,
) -> StudentDashboardService:
    """Build one request-scoped dashboard service from canonical analytics."""

    student_service = StudentService(StudentRepository(database_session))
    progress_service = ProgressService(ProgressRepository(database_session))
    study_right_service = StudyRightService(
        StudyRightRepository(database_session)
    )
    event_service = EventService(EventRepository(database_session))
    _memoize_dashboard_evidence(
        student_service,
        progress_service,
        study_right_service,
        event_service,
    )
    risk_service = AcademicRiskScoringService(
        DelayDetectionService(progress_service),
        StudyRightRiskService(study_right_service, student_service),
        event_service,
        TutorMeetingRiskService(TutorMeetingRepository(database_session)),
    )
    return StudentDashboardService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        event_service=event_service,
        academic_health_service=AcademicHealthScoreService(risk_service),
        academic_risk_service=risk_service,
    )


def _memoize_dashboard_evidence(
    student_service: StudentService,
    progress_service: ProgressService,
    study_right_service: StudyRightService,
    event_service: EventService,
) -> None:
    """Reuse overlapping evidence reads for the lifetime of one API request."""

    student_service.get_student = lru_cache(maxsize=None)(
        student_service.get_student
    )
    progress_service.get_progress = lru_cache(maxsize=None)(
        progress_service.get_progress
    )
    study_right_service.get_study_right = lru_cache(maxsize=None)(
        study_right_service.get_study_right
    )
    event_service.get_upcoming_events = lru_cache(maxsize=None)(
        event_service.get_upcoming_events
    )


StudentDashboardServiceDep = Annotated[
    StudentDashboardService,
    Depends(get_student_dashboard_service),
]
