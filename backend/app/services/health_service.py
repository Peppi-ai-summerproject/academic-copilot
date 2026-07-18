from sqlalchemy import text
from sqlalchemy.orm import Session


class HealthService:
    def get_status(self) -> dict[str, str]:
        return {"status": "healthy"}

    def get_database_status(
        self,
        database_session: Session,
    ) -> dict[str, str]:
        database_session.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }