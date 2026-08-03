import logging
from typing import Protocol

from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, WorkflowStatus
from app.agents.workflow import create_academic_agent_workflow
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.session_service import SessionService, session_service

logger = logging.getLogger(__name__)


class AgentWorkflow(Protocol):
    async def run(self, state: AgentState) -> AgentState: ...


class ChatService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        workflow: AgentWorkflow,
    ) -> None:
        self._session_service = session_service
        self._workflow = workflow

    async def process_message(
        self,
        request: ChatRequest,
    ) -> ChatResponse:
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
            reply = await self._run_workflow(request)
        else:
            reply = self._build_non_workflow_reply(request, session.message_count)

        self._session_service.add_assistant_message(
            telegram_user_id=request.telegram_user_id,
            reply=reply,
        )
        

        return ChatResponse(reply=reply)

    async def _run_workflow(self, request: ChatRequest) -> str:
        state = create_initial_state(
            user_message=request.message,
            student_id=request.student_id,
            telegram_user_id=request.telegram_user_id,
            telegram_chat_id=request.telegram_chat_id,
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
            return "I could not complete the academic analysis. Please try again."

        return _format_workflow_reply(result)

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
)
