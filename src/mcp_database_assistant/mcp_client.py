"""MCP client that connects to the database server over stdio."""

from __future__ import annotations

import sys
import json
import os
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters


class DatabaseMCPClient:
    """Owns the MCP connection; it never imports or opens SQLite."""

    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        # Streamlit Community Cloud runs the app from the source checkout. The
        # app can import this package because its entry-point directory is on
        # sys.path, but the child started from the repository root cannot
        # resolve a src-layout package unless we pass that path explicitly.
        source_root = project_root / "src"
        child_env = os.environ.copy()
        existing_pythonpath = child_env.get("PYTHONPATH")
        child_env["PYTHONPATH"] = os.pathsep.join(
            str(path) for path in (source_root, existing_pythonpath) if path
        )
        self.server = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_database_assistant.server"],
            env=child_env,
            cwd=project_root,
        )
        self.client: Client | None = None

    async def __aenter__(self) -> "DatabaseMCPClient":
        self.client = Client(self.server)
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.client is not None:
            await self.client.__aexit__(exc_type, exc, traceback)
            self.client = None

    async def list_tools(self) -> list[Any]:
        if self.client is None:
            raise RuntimeError("MCP client is not connected.")
        return (await self.client.list_tools()).tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("MCP client is not connected.")
        result = await self.client.call_tool(name, arguments)
        if result.is_error:
            message = " ".join(getattr(item, "text", "") for item in result.content).strip()
            return {"error": message or "The MCP tool reported an error."}
        if result.structured_content is not None:
            return result.structured_content
        text = " ".join(getattr(item, "text", "") for item in result.content).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
        return parsed if isinstance(parsed, dict) else {"result": parsed}

