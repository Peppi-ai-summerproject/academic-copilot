from app.agents.base import AgentResult
from app.agents.reducers import (
    append_completed_agents,
    append_errors,
    append_warnings,
    merge_agent_results,
)


def build_progress_result() -> AgentResult:
    return AgentResult(
        agent_name="ProgressAnalysisAgent",
        route="progress",
        status="SUCCESS",
        summary="Progress analysis complete.",
        data={"completed_ects": 30},
    )


def test_merge_agent_results_adds_new_result() -> None:
    current = {}
    update = {"progress": build_progress_result()}

    merged = merge_agent_results(current, update)

    assert merged["progress"].summary == "Progress analysis complete."


def test_merge_agent_results_replaces_existing_result() -> None:
    current = {"progress": build_progress_result()}
    updated = AgentResult(
        agent_name="ProgressAnalysisAgent",
        route="progress",
        status="SUCCESS",
        summary="Progress analysis updated.",
        data={"completed_ects": 35},
    )

    merged = merge_agent_results(current, {"progress": updated})

    assert merged["progress"].summary == "Progress analysis updated."
    assert merged["progress"].data["completed_ects"] == 35


def test_merge_agent_results_handles_empty_updates() -> None:
    result = merge_agent_results({}, None)

    assert result == {}


def test_append_warnings_accumulates_warnings() -> None:
    result = append_warnings(["previous warning"], ["new warning"])

    assert result == ["previous warning", "new warning"]


def test_append_errors_accumulates_errors() -> None:
    result = append_errors(["previous error"], ["new error"])

    assert result == ["previous error", "new error"]


def test_append_completed_agents_returns_unique_list() -> None:
    result = append_completed_agents(["progress"], ["progress", "risk"])

    assert result == ["progress", "risk"]


def test_agent_result_rejects_invalid_status() -> None:
    try:
        AgentResult(
            agent_name="ProgressAnalysisAgent",
            route="progress",
            status="INVALID",
            summary="Invalid status.",
        )
    except ValueError as error:
        assert "Invalid agent status" in str(error)
    else:
        raise AssertionError("Expected ValueError for invalid agent status")


def test_shared_state_flow_with_partial_updates() -> None:
    current_results = {}
    progress_result = build_progress_result()
    next_results = merge_agent_results(current_results, {"progress": progress_result})
    warnings = append_warnings([], ["Curriculum not found."])
    errors = append_errors([], [])
    completed = append_completed_agents([], ["progress"])

    assert "progress" in next_results
    assert warnings == ["Curriculum not found."]
    assert errors == []
    assert completed == ["progress"]
