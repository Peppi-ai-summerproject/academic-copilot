from app.mcp import get_server


def test_demo_calls_ping_tool():
    server = get_server()
    tool = server._tool_manager.get_tool("ping")
    assert tool is not None
    result = tool.fn()
    assert isinstance(result, dict)
    assert result.get("status") == "ok"
    assert result.get("service") == "academic-copilot-mcp"
