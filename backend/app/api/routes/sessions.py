from fastapi import APIRouter, HTTPException, status

from app.schemas.session import UserSession
from app.services.session_service import session_service

router = APIRouter()


@router.get(
    "/{telegram_user_id}",
    response_model=UserSession,
)
async def get_user_session(
    telegram_user_id: int,
) -> UserSession:
    session = session_service.get_session(
        telegram_user_id,
    )

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User session was not found.",
        )

    return session


@router.delete(
    "/{telegram_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_session(
    telegram_user_id: int,
) -> None:
    deleted = session_service.delete_session(
        telegram_user_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User session was not found.",
        )