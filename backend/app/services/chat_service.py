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
from app.services.fallback_response_service import FallbackResponseService
from app.services.academic_entity_resolver import AcademicEntityResolver
from app.gateways.academic_tools import MCPAcademicToolGateway
from app.services.session_service import SessionService, session_service
from app.services.conversation_memory import (
    ConversationMemoryStore,
    MemoryScope,
    SQLAlchemyConversationMemoryStore,
    telegram_owner_reference,
)
from app.db.database import SessionLocal
from app.services.conversation_context import (
    canonical_entities,
    entity_for,
    merge_canonical_entities,
    missing_entities,
)

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
        fallback_responses: FallbackResponseService | None = None,
        entity_resolver: AcademicEntityResolver | None = None,
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
        self._fallback_responses = fallback_responses or FallbackResponseService()
        self._entity_resolver = entity_resolver or AcademicEntityResolver(MCPAcademicToolGateway())

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
        fallback_interaction_status = "failed"
        stored_entities = canonical_entities(memory.resolved_entities if memory else [])
        resolved_entities: list[dict] = list(stored_entities)
        query_parameters: dict = {}
        if selected_routes:
            routing_failure = self._validate_explicit_routes(selected_routes)
        else:
            try:
                intent_result = self._intent_detector.detect(request.message)
                detected_intent = intent_result.intent
                if intent_result.intent == "academic_data":
                    query_parameters = {
                        "capability": intent_result.capability,
                        "query_parameters": intent_result.parameters or {},
                    }
                    current_resolutions: list[dict] = []
                    for entity_type, reference in intent_result.entity_references:
                        resolution = await self._entity_resolver.resolve(entity_type, reference)  # type: ignore[arg-type]
                        active_group = entity_for(current_resolutions, "STUDENT_GROUP") or entity_for(
                            stored_entities, "STUDENT_GROUP"
                        )
                        narrow = getattr(self._entity_resolver, "narrow_ambiguous_course_to_group", None)
                        if (
                            entity_type == "COURSE"
                            and resolution.status == "AMBIGUOUS"
                            and active_group is not None
                            and callable(narrow)
                        ):
                            resolution = await narrow(resolution, active_group["canonical_id"])
                        current_resolutions.append(resolution.as_dict())
                    # A bare named lookup is historically classified as a student.
                    # Resolve it through the remaining canonical namespaces without
                    # guessing or bypassing AcademicEntityResolver.
                    if (
                        intent_result.capability == "student_lookup"
                        and len(current_resolutions) == 1
                        and current_resolutions[0]["status"] == "NOT_FOUND"
                    ):
                        reference = intent_result.entity_references[0][1]
                        for entity_type, capability in (
                            ("TEACHER", "teacher_lookup"),
                            ("COURSE", "course_lookup"),
                            ("STUDENT_GROUP", "group_lookup"),
                        ):
                            alternate = await self._entity_resolver.resolve(entity_type, reference)
                            if alternate.status != "NOT_FOUND":
                                current_resolutions = [alternate.as_dict()]
                                query_parameters["capability"] = capability
                                break
                    unresolved = [row for row in current_resolutions if row["status"] != "RESOLVED"]
                    if unresolved:
                        routing_failure = _resolution_fallback(unresolved[0])
                        fallback_interaction_status = "completed"
                    else:
                        resolved_entities = merge_canonical_entities(stored_entities, current_resolutions)
                    if query_parameters.get("capability") == "academic_lookup" and current_resolutions and not unresolved:
                        query_parameters["capability"] = (
                            "group_lookup" if current_resolutions[0]["entity_type"] == "STUDENT_GROUP" else "course_lookup"
                        )
                    missing = missing_entities(query_parameters.get("capability"), resolved_entities)
                    if (
                        query_parameters.get("capability") == "teacher_contact"
                        and not intent_result.entity_references
                        and entity_for(resolved_entities, "TEACHER") is None
                        and entity_for(resolved_entities, "STUDENT") is not None
                    ):
                        query_parameters["capability"] = "student_lookup"
                        missing = ()
                    if not unresolved and missing:
                        routing_failure = _missing_entity_fallback(missing)
                        fallback_interaction_status = "completed"
                routing_result = self._agent_selector.select(intent_result)
                plan = self._dependency_resolver.resolve(routing_result)
                if plan.succeeded:
                    if routing_failure is None:
                        selected_routes = list(plan.ordered_routes)
                        if (
                            request.student_id is None
                            and entity_for(resolved_entities, "STUDENT") is None
                            and self._fallback_responses.requires_student_context(
                                plan.ordered_routes
                            )
                        ):
                            routing_failure = (
                                self._fallback_responses.for_missing_student_context()
                            )
                            fallback_interaction_status = "completed"
                            selected_routes = []
                else:
                    if intent_result.intent in {"general", "unknown"}:
                        routing_failure = self._fallback_responses.for_non_academic(
                            intent_result
                        )
                        fallback_interaction_status = "completed"
                    else:
                        routing_failure = (
                            self._fallback_responses.for_internal_routing_failure()
                        )
                    if plan.errors and intent_result.intent not in {"general", "unknown"}:
                        logger.warning("Automatic academic routing failed: %s", plan.reason)
            except Exception:
                logger.exception("Automatic academic routing failed unexpectedly.")
                routing_failure = self._fallback_responses.for_internal_routing_failure()

        if selected_routes and routing_failure is None:
            reply, interaction_status = await self._run_workflow(
                request,
                selected_routes=selected_routes,
                detected_intent=detected_intent,
                conversation_id=conversation_id,
                memory=memory,
                include_telegram_context=memory_scope is None,
                resolved_entities=resolved_entities,
                query_parameters=query_parameters,
            )
        else:
            reply = routing_failure or "No academic route is available for this request."
            interaction_status = fallback_interaction_status

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
                    resolved_entities=resolved_entities,
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
        resolved_entities: list[dict],
        query_parameters: dict,
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
        state.resolved_entities = resolved_entities
        student = entity_for(resolved_entities, "STUDENT")
        if state.student_id is None and student is not None:
            state.student_id = student["canonical_id"]
            state.student_name = student.get("display_name")
        state.parameters.update(query_parameters)

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
                return self._fallback_responses.for_internal_routing_failure()
        return None


def _format_workflow_reply(state: AgentState) -> str:
    if (
        state.workflow_status is not WorkflowStatus.FAILED
        and isinstance(state.final_response, str)
        and state.final_response.strip()
    ):
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


def _resolution_fallback(entity: dict) -> str:
    label = str(entity.get("entity_type", "entity")).lower().replace("_", " ")
    if entity.get("status") == "AMBIGUOUS":
        candidates = entity.get("candidates") or []
        names = [str(row.get("student_number") or row.get("group_code") or row.get("course_code") or row.get("name") or row.get("group_name") or row.get("course_name")) for row in candidates]
        return f"I found multiple matching {label}s: {', '.join(names)}. Which one do you mean?"
    return f"I could not find the requested {label}."


def _missing_entity_fallback(entity_types: tuple[str, ...]) -> str:
    labels = {"STUDENT": "student", "COURSE": "course", "TEACHER": "teacher", "STUDENT_GROUP": "student group"}
    if len(entity_types) == 1:
        return f"Which {labels[entity_types[0]]} do you mean?"
    return "Which " + " and ".join(labels[kind] for kind in entity_types) + " do you mean?"


_agent_registry = create_default_agent_registry()
chat_service = ChatService(
    session_service=session_service,
    workflow=create_academic_agent_workflow(registry=_agent_registry),
    memory_store=SQLAlchemyConversationMemoryStore(SessionLocal),
    registry=_agent_registry,
)
