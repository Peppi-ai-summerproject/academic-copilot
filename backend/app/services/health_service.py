class HealthService:
    def get_status(self) -> dict[str, str]:
        return {"status": "healthy"}