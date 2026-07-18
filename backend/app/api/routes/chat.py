from fastapi import APIRouter

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service

router = APIRouter()


@router.post(
    "/messages",
    response_model=ChatResponse,
)
async def process_chat_message(
    request: ChatRequest,
) -> ChatResponse:
    return await chat_service.process_message(request)