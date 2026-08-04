import secrets

from fastapi import APIRouter, Header

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service
from app.core.config import settings

router = APIRouter()


@router.post(
    "/messages",
    response_model=ChatResponse,
)
async def process_chat_message(
    request: ChatRequest,
    x_internal_service_key: str | None = Header(default=None),
) -> ChatResponse:
    trusted_telegram = bool(
        settings.internal_service_key
        and isinstance(x_internal_service_key, str)
        and x_internal_service_key
        and secrets.compare_digest(
            x_internal_service_key,
            settings.internal_service_key,
        )
    )
    return await chat_service.process_message(
        request,
        trusted_telegram=trusted_telegram,
    )
