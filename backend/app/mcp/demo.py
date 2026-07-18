"""MCP demo client

Runs a simple local demonstration of the MCP server ping tool.
This script imports the local server and calls the registered `ping` tool directly.
"""

from app.mcp import get_server


def run_demo() -> None:
    server = get_server()
    print("Registered tools:", [t.name for t in server._tool_manager.list_tools()])
    tool = server._tool_manager.get_tool("ping")
    if tool is None:
        raise SystemExit("Ping tool not found")
    result = tool.fn()
    print("Ping result:", result)


if __name__ == "__main__":
    run_demo()
