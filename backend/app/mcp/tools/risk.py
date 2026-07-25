from sqlalchemy.exc import SQLAlchemyError

from app.db.database import SessionLocal
from app.repositories.risk_repository import RiskRepository
from app.services.risk_service import RiskService


def find_students_at_risk(
    programme_code: str | None = None,
):
    db = SessionLocal()

    try:
        repository = RiskRepository(db)
        service = RiskService(repository)

        return service.find_students_at_risk(
            programme_code=programme_code,
        )

    except SQLAlchemyError:
        return {
            "success": False,
            "error": "DATABASE_ERROR",
            "message": "Failed to identify students at risk.",
        }

    finally:
        db.close()