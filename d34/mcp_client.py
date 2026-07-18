"""Async stdio client for the d34 file MCP server."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_FILE = Path(__file__).resolve().with_name("mcp_server.py")


class ProjectMCPClient:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ProjectMCPClient":
        if not self.project_root.is_dir():
            raise ValueError(f"Каталог проекта не найден: {self.project_root}")
        env = os.environ.copy()
        env["D34_PROJECT_ROOT"] = str(self.project_root)
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER_FILE)], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def tool_definitions(self) -> list[dict[str, Any]]:
        if self._session is None:
            raise RuntimeError("MCP-клиент не подключён")
        response = await self._session.list_tools()
        return [{"name": tool.name, "description": tool.description or "", "input_schema": tool.inputSchema} for tool in response.tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError("MCP-клиент не подключён")
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            message = "\n".join(getattr(block, "text", str(block)) for block in result.content)
            raise RuntimeError(message or f"MCP tool {name} failed")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured.get("result", structured)
        for block in result.content:
            if getattr(block, "text", None):
                return json.loads(block.text)
        return {}
