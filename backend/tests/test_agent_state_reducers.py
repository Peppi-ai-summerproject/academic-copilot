"""Unit tests for state reducers — Issue #87."""

import pytest
from app.agents.reducers import append_all, append_unique, merge_agent_results
from app.agents.types import AgentResult


def _r(name, summary=""):
    return AgentResult(
        agent_name=name,
        route=name,
        status="SUCCESS",
        summary=summary,
    )


def test_merge_adds_new_agent_result():
    merged = merge_agent_results({"progress": _r("progress")}, {"risk": _r("risk")})
    assert "progress" in merged and "risk" in merged

def test_merge_preserves_existing_results():
    merged = merge_agent_results({"progress": _r("progress", "on track")}, {"risk": _r("risk")})
    assert merged["progress"].summary == "on track"

def test_merge_same_agent_replaces_previous():
    merged = merge_agent_results({"progress": _r("progress", "first")}, {"progress": _r("progress", "second")})
    assert merged["progress"].summary == "second"

def test_merge_empty_update_returns_copy_of_current():
    current = {"progress": _r("progress")}
    merged = merge_agent_results(current, {})
    assert merged == current and merged is not current

def test_merge_empty_current_returns_copy_of_update():
    update = {"progress": _r("progress")}
    merged = merge_agent_results({}, update)
    assert merged == update and merged is not update

def test_merge_both_empty_returns_empty_dict():
    assert merge_agent_results({}, {}) == {}

def test_merge_does_not_mutate_current():
    current = {"progress": _r("progress")}
    merge_agent_results(current, {"risk": _r("risk")})
    assert set(current.keys()) == {"progress"}

def test_append_unique_adds_new_items():
    result = append_unique(["progress"], ["risk"])
    assert "risk" in result and "progress" in result

def test_append_unique_skips_duplicates():
    result = append_unique(["progress"], ["progress", "risk"])
    assert result.count("progress") == 1 and "risk" in result

def test_append_unique_empty_update():
    assert append_unique(["progress"], []) == ["progress"]

def test_append_unique_empty_current():
    assert append_unique([], ["progress", "risk"]) == ["progress", "risk"]

def test_append_unique_both_empty():
    assert append_unique([], []) == []

def test_append_unique_does_not_mutate_current():
    current = ["progress"]
    append_unique(current, ["risk"])
    assert current == ["progress"]

def test_append_unique_preserves_order():
    assert append_unique(["progress"], ["risk", "calendar"]) == ["progress", "risk", "calendar"]

def test_append_all_adds_all_including_duplicates():
    result = append_all(["warning A"], ["warning A", "warning B"])
    assert result.count("warning A") == 2 and "warning B" in result

def test_append_all_empty_update():
    assert append_all(["warning A"], []) == ["warning A"]

def test_append_all_empty_current():
    assert append_all([], ["warning A"]) == ["warning A"]

def test_append_all_does_not_mutate_current():
    current = ["warning A"]
    append_all(current, ["warning B"])
    assert current == ["warning A"]

def test_shared_state_exchange_between_fake_nodes():
    from app.agents.state import create_initial_state
    from app.agents.reducers import merge_agent_results, append_unique

    state = create_initial_state(user_message="How is S001?", student_id=1, request_id="test-001")

    progress_result = AgentResult(
        agent_name="progress",
        route="progress",
        status="SUCCESS",
        summary="30 ECTS behind.",
        data={
            "completed_ects": 90,
            "expected_ects": 120,
            "status": "BEHIND",
        },
    )
    state.agent_results = merge_agent_results(state.agent_results, {"progress": progress_result})
    state.completed_agents = append_unique(state.completed_agents, ["progress"])
    state.step_count += 1

    assert "progress" in state.agent_results
    assert state.agent_results["progress"].data["status"] == "BEHIND"
    assert "progress" in state.completed_agents
    assert state.step_count == 1

    progress_data = state.agent_results.get("progress")
    rec_result = AgentResult(
        agent_name="recommendation",
        route="recommendation",
        status="SUCCESS",
        summary="Schedule meeting.",
        data={
            "action": "schedule_meeting",
            "priority": "HIGH",
        },
    )
    state.agent_results = merge_agent_results(state.agent_results, {"recommendation": rec_result})
    state.completed_agents = append_unique(state.completed_agents, ["recommendation"])
    state.step_count += 1

    assert "progress" in state.agent_results
    assert "recommendation" in state.agent_results
    assert state.agent_results["recommendation"].data["priority"] == "HIGH"
    assert state.step_count == 2
    assert state.completed_agents == ["progress", "recommendation"]
