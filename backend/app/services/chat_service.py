import logging
from typing import Protocol
from uuid import UUID, uuid4

from app.agents.agent_selection import AgentSelector
from app.agents.dependency_resolution import DependencyResolver
from app.agents.intent_detection import IntentDetector
from app.agents.registry import AgentRegistry
from app.agents.routing import SUPPORTED_ROUTES
from app.agents.state import AgentState, create_initial_state
from app.agents.types import AgentResult, AgentRoute, WorkflowStatus
from app.agents.workflow import create_academic_agent_workflow, create_default_agent_registry
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
        registry: AgentRegistry | None = None,
        intent_detector: IntentDetector | None = None,
        agent_selector: AgentSelector | None = None,
        dependency_resolver: DependencyResolver | None = None,
    ) -> None:
        self._session_service = session_service
        self._workflow = workflow
        self._memory_store = memory_store
        self._registry = registry or create_default_agent_registry()
        self._intent_detector = intent_detector or IntentDetector()
        self._agent_selector = agent_selector or AgentSelector(self._registry)
        self._dependency_resolver = dependency_resolver or DependencyResolver(
            self._registry
        )

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

        selected_routes = list(request.selected_agents)
        detected_intent: str | None = None
        routing_failure: str | None = None

        if selected_routes:
            routing_failure = self._validate_explicit_routes(selected_routes)
        else:
            try:
                intent_result = self._intent_detector.detect(request.message)
                detected_intent = intent_result.intent
                routing_result = self._agent_selector.select(intent_result)
                plan = self._dependency_resolver.resolve(routing_result)
                if plan.succeeded:
                    selected_routes = list(plan.ordered_routes)
                else:
                    routing_failure = _automatic_routing_fallback(
                        intent_result.intent,
                        intent_result.is_ambiguous,
                        plan.status,
                    )
                    if plan.errors:
                        logger.warning("Automatic academic routing failed: %s", plan.reason)
            except Exception:
                logger.exception("Automatic academic routing failed unexpectedly.")
                routing_failure = (
                    "I could not route this academic request safely. Please clarify "
                    "the academic information you need."
                )

        if selected_routes and routing_failure is None:
            reply, interaction_status = await self._run_workflow(
                request,
                selected_routes=selected_routes,
                detected_intent=detected_intent,
                conversation_id=conversation_id,
                memory=memory,
                include_telegram_context=memory_scope is None,
            )
        else:
            reply = routing_failure or "No academic route is available for this request."
            interaction_status = "completed" if detected_intent in {"general", "unknown"} else "failed"

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
                    selected_agents=[str(route) for route in selected_routes],
                    interaction_status=interaction_status,
                )
            except Exception:
                logger.warning("Conversation memory could not be saved safely.")

        return ChatResponse(reply=reply, conversation_id=conversation_id)

    async def _run_workflow(
        self,
        request: ChatRequest,
        *,
        selected_routes: list[AgentRoute],
        detected_intent: str | None,
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
        state.intent = detected_intent
        state.selected_agents = list(selected_routes)

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

    def _validate_explicit_routes(self, routes: list[AgentRoute]) -> str | None:
        for route in routes:
            if (
                route == "finish"
                or route not in SUPPORTED_ROUTES
                or self._registry.get(route) is None
            ):
                logger.warning("Explicit academic route is not executable: %s", route)
                return "I could not route this academic request safely."
        return None


def _automatic_routing_fallback(
    intent: str,
    ambiguous: bool,
    plan_status: str,
) -> str:
    if intent == "general":
        return "No academic analysis was requested."
    if intent == "unknown" and ambiguous:
        return "Please clarify which academic information you want me to check."
    if intent == "unknown":
        return "I could not match that request to a supported academic analysis."
    logger.warning("Academic execution plan was rejected with status: %s", plan_status)
    return "I could not route this academic request safely. Please try again or clarify it."


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


_agent_registry = create_default_agent_registry()
chat_service = ChatService(
    session_service=session_service,
    workflow=create_academic_agent_workflow(registry=_agent_registry),
    memory_store=SQLAlchemyConversationMemoryStore(SessionLocal),
    registry=_agent_registry,
)
