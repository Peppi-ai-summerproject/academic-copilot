# Week 1 Research: MCP Protocol

## Overview

This research document covers issue #7: Study MCP Protocol.

The goal is to understand the Model Context Protocol (MCP), how MCP servers expose tools, and how agents communicate with external services.

## Objectives

- Understand MCP architecture
- Learn how MCP servers expose tools
- Study tool registration
- Explore communication between agents and tools

## Acceptance Criteria

- MCP documentation reviewed
- Tool-calling workflow understood
- Demo example prepared
- Research summary completed

## What is MCP?

The Model Context Protocol (MCP) is a standard for connecting language models and AI agents to external tools and services.

Key ideas:

- Agents send requests to an MCP server.
- The server exposes registered tools.
- Each tool can be invoked by name with arguments.
- The agent receives tool results and continues the workflow.

## Why MCP for Academic Copilot?

MCP is useful because it separates tool execution from the language model's reasoning.

- Keeps the backend modular and testable
- Allows the model to call precise services instead of relying on hallucinated knowledge
- Enables integration with database-backed business logic, Telegram, and other external APIs

## MCP Architecture

Typical MCP architecture consists of:

1. **MCP server**
   - Registers available tool functions
   - Accepts tool execution requests
   - Returns structured responses
2. **Agent / model**
   - Decides when and which tool to call
   - Sends tool requests to the server
   - Uses returned data to generate responses
3. **Tools**
   - Defined as functions or endpoints
   - Encapsulate application logic
   - May query databases, call external APIs, or return computed results

## Tool registration and workflow

A tool is usually registered with:

- tool name
- function reference
- metadata describing inputs and outputs

Workflow:

1. Agent asks MCP server for available tools.
2. Agent chooses the correct tool for the task.
3. Agent sends tool name and arguments.
4. MCP server executes the tool.
5. Tool returns results.
6. Agent uses the result in its next step.

## Demo example

In this repository, the MCP demo is implemented with a simple `ping` tool.

- `backend/app/mcp/tools/health.py` defines the `ping` tool.
- `backend/app/mcp/server.py` initializes the MCP server and registers tools.
- `backend/app/mcp/demo.py` demonstrates calling the `ping` tool.

The ping tool proves the tool-calling workflow:

- Agent requests tool execution
- MCP server runs the tool
- Response is returned to the caller

## Key findings

- MCP is a strong fit for exposing isolated backend capabilities to AI agents.
- Tool registration should remain simple and declarative.
- The backend should keep MCP tools as thin wrappers around service logic.
- MCP is especially useful where the model must avoid hallucinating and rely on deterministic services.

## Conclusions

The MCP research confirms that this project should use MCP for agent-tool communication.
The current implementation is a valid proof of concept, and the next step is to expand MCP tools for academic workflows.
