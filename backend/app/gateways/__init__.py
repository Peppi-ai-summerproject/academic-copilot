"""Application gateways used to isolate agents from infrastructure details."""

from app.gateways.academic_tools import (
    AcademicToolGateway,
    AcademicToolGatewayError,
    MCPAcademicToolGateway,
)

__all__ = [
    "AcademicToolGateway",
    "AcademicToolGatewayError",
    "MCPAcademicToolGateway",
]
