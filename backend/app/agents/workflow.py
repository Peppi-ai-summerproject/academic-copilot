"""LangGraph orchestration for academic agents — Issue #167."""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from app.agents.registry import AgentRegistry
from app.agents.state import AgentState
from app.agents.types import AgentResult, AgentRoute, WorkflowStatus
from app.gateways.academic_tools import AcademicToolGateway, MCPAcademicToolGateway


class AcademicAgentWorkflow:
    """Execute selected academic agents against one shared ``AgentState``.

    The workflow owns orchestration only. Academic data access remains behind
    ``AcademicToolGateway`` and individual agents remain responsible for their
    domain logic.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        gateway: AcademicToolGateway | None = None,
    ) -> None:
        self._registry = registry
        self._gateway = gateway or MCPAcademicToolGateway()
        self._graph = self._build_graph()

    async def run(self, state: AgentState) -> AgentState:
        """Run the compiled graph and return the canonical state model."""
        result = await self._graph.ainvoke(
            state,
            config={"recursion_limit": state.max_steps + 4},
        )
        return AgentState.model_validate(result)

    def _build_graph(self) -> Any:
        builder = StateGraph(AgentState)
        builder.add_node("prepare", self._prepare)
        builder.add_node("execute_agent", self._execute_agent)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "prepare")
        builder.add_conditional_edges(
            "prepare",
            self._next_after_prepare,
            {"execute": "execute_agent", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "execute_agent",
            self._next_after_execution,
            {"execute": "execute_agent", "finalize": "finalize"},
        )
        builder.add_edge("finalize", END)
        return builder.compile()

    def _prepare(self, state: AgentState) -> dict[str, Any]:
        selected = _unique(state.selected_agents)
        completed = set(state.completed_agents)
        pending = [route for route in selected if route not in completed]
        return {
            "selected_agents": selected,
            "pending_agents": pending,
            "current_agent": None,
            "workflow_status": WorkflowStatus.RUNNING,
        }

    @staticmethod
    def _next_after_prepare(state: AgentState) -> str:
        if not state.pending_agents or state.is_step_limit_reached():
            return "finalize"
        return "execute"

    async def _execute_agent(self, state: AgentState) -> dict[str, Any]:
        route_name = state.pending_agents[0]
        remaining = state.pending_agents[1:]
        completed = _unique([*state.completed_agents, route_name])
        results = dict(state.agent_results)
        warnings = list(state.warnings)
        errors = list(state.errors)

        agent_type = self._registry.get(cast(AgentRoute, route_name))
        if agent_type is None:
            errors.append(f"No registered agent for route '{route_name}'.")
        else:
            try:
                agent = agent_type(self._gateway)
                result = await agent.run(state)
                if not isinstance(result, AgentResult):
                    raise TypeError(
                        f"Agent '{route_name}' returned {type(result).__name__}; "
                        "expected AgentResult."
                    )
                results[route_name] = result
                warnings.extend(result.warnings)
                errors.extend(result.errors)
            except Exception as exc:
                errors.append(f"Agent '{route_name}' raised an exception: {exc}")

        return {
            "pending_agents": remaining,
            "completed_agents": completed,
            "current_agent": route_name,
            "step_count": state.step_count + 1,
            "agent_results": results,
            "warnings": warnings,
            "errors": errors,
        }

    @staticmethod
    def _next_after_execution(state: AgentState) -> str:
        if state.pending_agents and not state.is_step_limit_reached():
            return "execute"
        return "finalize"

    @staticmethod
    def _finalize(state: AgentState) -> dict[str, Any]:
        return {
            "current_agent": None,
            "workflow_status": _final_status(state),
        }


def create_default_agent_registry() -> AgentRegistry:
    """Create the production registry for agents supported by Issue #167."""
    from app.agents.progress_analysis_agent import ProgressAnalysisAgent
    from app.agents.risk_detection_agent import RiskDetectionAgent
    from app.agents.study_rights_agent import StudyRightsAgent

    registry = AgentRegistry()
    registry.register("progress", ProgressAnalysisAgent)
    registry.register("study_rights", StudyRightsAgent)
    registry.register("risk", RiskDetectionAgent)
    return registry


def create_academic_agent_workflow(
    *,
    registry: AgentRegistry | None = None,
    gateway: AcademicToolGateway | None = None,
) -> AcademicAgentWorkflow:
    """Build the production workflow with replaceable dependencies."""
    return AcademicAgentWorkflow(
        registry=registry or create_default_agent_registry(),
        gateway=gateway,
    )


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _final_status(state: AgentState) -> WorkflowStatus:
    results = [
        result
        for result in state.agent_results.values()
        if isinstance(result, AgentResult)
    ]
    successful = sum(result.status == "SUCCESS" for result in results)
    partial = sum(result.status in {"PARTIAL", "SKIPPED"} for result in results)
    failed = sum(result.status == "FAILED" for result in results)
    unfinished = bool(state.pending_agents)
    orchestration_errors = len(state.errors) > sum(len(r.errors) for r in results)

    if not state.selected_agents:
        return WorkflowStatus.COMPLETED
    if successful == len(state.selected_agents) and not unfinished:
        return WorkflowStatus.COMPLETED
    if successful or partial:
        return WorkflowStatus.PARTIAL
    if failed or orchestration_errors or unfinished:
        return WorkflowStatus.FAILED
    return WorkflowStatus.FAILED
