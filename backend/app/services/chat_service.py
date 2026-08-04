import logging
from typing import Protocol
from uuid import UUID, uuid4

from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, WorkflowStatus
from app.agents.workflow import create_academic_agent_workflow
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.session_service import SessionService, session_service
from app.services.conversation_memory import (
    ConversationMemoryStore,
    MemoryScope,
    SQLAlchemyConversationMemoryStore,
    telegram_owner_reference,
)
from app.db.database import SessionLocal

logger = logging.getLogger(__name__)


class AgentWorkflow(Protocol):
    async def run(self, state: AgentState) -> AgentState: ...


class ChatService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        workflow: AgentWorkflow,
        memory_store: ConversationMemoryStore | None = None,
    ) -> None:
        self._session_service = session_service
        self._workflow = workflow
        self._memory_store = memory_store

    async def process_message(
        self,
        request: ChatRequest,
        *,
        trusted_telegram: bool = False,
    ) -> ChatResponse:
        conversation_id, memory_scope = self._resolve_memory_scope(
            request, trusted_telegram=trusted_telegram
        )
        memory = None
        if memory_scope is not None and self._memory_store is not None:
            try:
                memory = self._memory_store.load(memory_scope)
            except Exception:
                logger.warning("Conversation memory could not be loaded safely.")
        session = self._session_service.update_session_message(
            telegram_user_id=request.telegram_user_id,
            telegram_chat_id=request.telegram_chat_id,
            username=request.username,
            message=request.message,
        )

        logger.info(
            "Processing chat message: "
            "user_id=%s chat_id=%s username=%s message_count=%s",
            request.telegram_user_id,
            request.telegram_chat_id,
            request.username,
            session.message_count,
        )

        if request.selected_agents:
            reply, interaction_status = await self._run_workflow(
                request,
                conversation_id=conversation_id,
                memory=memory,
                include_telegram_context=memory_scope is None,
            )
        else:
            reply = self._build_non_workflow_reply(request, session.message_count)
            interaction_status = "completed"

        self._session_service.add_assistant_message(
            telegram_user_id=request.telegram_user_id,
            reply=reply,
        )
        

        if (
            memory_scope is not None
            and self._memory_store is not None
            and interaction_status in {"completed", "partial"}
        ):
            try:
                self._memory_store.save_turn(
                    memory_scope,
                    user_message=request.message,
                    assistant_message=reply,
                    selected_agents=[str(route) for route in request.selected_agents],
                    interaction_status=interaction_status,
                )
            except Exception:
                logger.warning("Conversation memory could not be saved safely.")

        return ChatResponse(reply=reply, conversation_id=conversation_id)

    async def _run_workflow(
        self,
        request: ChatRequest,
        *,
        conversation_id: UUID,
        memory,
        include_telegram_context: bool,
    ) -> tuple[str, str]:
        state = create_initial_state(
            user_message=request.message,
            student_id=request.student_id,
            conversation_id=str(conversation_id),
            telegram_user_id=(request.telegram_user_id if include_telegram_context else None),
            telegram_chat_id=(request.telegram_chat_id if include_telegram_context else None),
            memory=memory,
        )
        state.selected_agents = list(request.selected_agents)

        try:
            result = await self._workflow.run(state)
        except Exception:
            logger.exception(
                "Academic workflow failed: user_id=%s chat_id=%s",
                request.telegram_user_id,
                request.telegram_chat_id,
            )
            return "I could not complete the academic analysis. Please try again.", "failed"

        return _format_workflow_reply(result), result.workflow_status.value

    def _resolve_memory_scope(
        self,
        request: ChatRequest,
        *,
        trusted_telegram: bool,
    ) -> tuple[UUID, MemoryScope | None]:
        if trusted_telegram and self._memory_store is not None:
            try:
                conversation_id = self._memory_store.resolve_telegram_conversation(
                    request.telegram_user_id,
                    request.telegram_chat_id,
                )
                return conversation_id, MemoryScope(
                    conversation_id=conversation_id,
                    owner_type="telegram",
                    owner_reference=telegram_owner_reference(
                        request.telegram_user_id,
                        request.telegram_chat_id,
                    ),
                    student_id=request.student_id,
                )
            except Exception:
                logger.warning("Telegram conversation mapping could not be resolved safely.")
        return request.conversation_id or uuid4(), None

    @staticmethod
    def _build_non_workflow_reply(
        request: ChatRequest,
        message_count: int,
    ) -> str:
        return (
            "Backend received your message successfully.\n\n"
            f"Message: {request.message}\n"
            f"Session message count: {message_count}"
        )


def _format_workflow_reply(state: AgentState) -> str:
    if isinstance(state.final_response, str) and state.final_response.strip():
        return state.final_response.strip()

    summaries = [
        result.summary.strip()
        for route in state.selected_agents
        if isinstance((result := state.agent_results.get(route)), AgentResult)
        and result.summary.strip()
    ]

    if summaries:
        body = "\n".join(f"- {summary}" for summary in summaries)
    elif state.workflow_status is WorkflowStatus.COMPLETED:
        body = "The academic analysis completed without a result summary."
    else:
        body = "No academic result is available."

    status_label = {
        WorkflowStatus.COMPLETED: "Academic analysis completed.",
        WorkflowStatus.PARTIAL: "Academic analysis partially completed.",
        WorkflowStatus.FAILED: "Academic analysis could not be completed.",
    }.get(state.workflow_status, "Academic analysis ended with an unknown status.")

    return f"{status_label}\n\n{body}"


chat_service = ChatService(
    session_service=session_service,
    workflow=create_academic_agent_workflow(),
    memory_store=SQLAlchemyConversationMemoryStore(SessionLocal),
)
