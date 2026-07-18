from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys

from app.mcp.server import create_server


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PING_RESPONSE = {
    "status": "ok",
    "service": "academic-copilot-mcp",
}


def test_server_can_be_imported_without_database_configuration() -> None:
    environment = os.environ.copy()
    for name in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_KEY"):
        environment.pop(name, None)

    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        str(BACKEND_ROOT)
        if not existing_python_path
        else os.pathsep.join((str(BACKEND_ROOT), existing_python_path))
    )

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.mcp.server import create_server; assert create_server() is not None",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_server_initializes_successfully() -> None:
    server = create_server()
    assert server is not None


def test_ping_tool_is_registered() -> None:
    server = create_server()
    tools = asyncio.run(server.list_tools())

    assert "ping" in {tool.name for tool in tools}


def test_ping_tool_returns_expected_payload() -> None:
    server = create_server()
    result = asyncio.run(server.call_tool("ping", {}))
    payload = result[1] if isinstance(result, tuple) else result

    assert payload == PING_RESPONSE
