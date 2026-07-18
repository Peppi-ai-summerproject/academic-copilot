# MCP server

## Install dependencies

From the backend directory:

```bash
python -m pip install -r requirements.txt
```

For local test dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

## Run locally

Start the MCP server with:

```bash
python -m app.mcp
```

The server uses the stdio transport by default and does not require the FastAPI app, Telegram bot, or database connection to start.

## Register future tools

Future tools should be added as plain functions in `app/mcp/tools/`, then explicitly registered in `app/mcp/registry.py`. Tool functions must delegate academic work to application services; they must not contain database queries or agent/Telegram orchestration.

```python
# app/mcp/tools/example.py
def example_tool() -> dict[str, str]:
    return {"status": "ok"}

# app/mcp/registry.py
from mcp.server.fastmcp import FastMCP

from app.mcp.tools.example import example_tool

def register_tools(server: FastMCP) -> None:
    server.add_tool(example_tool, name="example_tool")
```

## Verify manually

Configure an MCP client with `backend` as its working directory, command `python`, and arguments `-m app.mcp`. Call the `ping` tool and confirm this response:

```json
{
  "status": "ok",
  "service": "academic-copilot-mcp"
}
```

To run the automated checks:

```bash
python -m pytest tests/test_mcp_server.py -q
```
