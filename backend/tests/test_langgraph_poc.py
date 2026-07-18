from app.research.langgraph_poc import demo


def test_langgraph_poc_runs():
    state = demo()
    assert state.get("a") == "done"
    assert state.get("b") == "done"
