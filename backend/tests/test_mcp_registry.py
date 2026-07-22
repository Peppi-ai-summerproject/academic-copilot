from __future__ import annotations

import asyncio

from mcp.server.fastmcp import FastMCP

from app.mcp.registry import register_tools

def test_register_tools_registers_ping() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}

    assert "ping" in tool_names


def test_registered_ping_has_description() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    ping_tool = next(tool for tool in tools if tool.name == "ping")

    assert ping_tool.description
    assert ping_tool.description == "Simple health check for the MCP server."


def test_register_tools_registers_get_student() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}

    assert "get_student" in tool_names

def test_registered_get_student_has_description() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    get_student_tool = next(
        tool for tool in tools if tool.name == "get_student"
    )

    assert get_student_tool.description
    assert (
        get_student_tool.description
        == (
            "Retrieve a student profile from the simulated Peppi database "
            "using the student's numeric database ID."
        )
    )


def test_register_tools_registers_get_study_right() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}

    assert "get_study_right" in tool_names


def test_registered_get_study_right_has_description() -> None:
    server = FastMCP(name="test-mcp-server")

    register_tools(server)

    tools = asyncio.run(server.list_tools())
    tool = next(
        tool for tool in tools if tool.name == "get_study_right"
    )

    assert tool.description
    assert "expiration" in tool.description.lower()