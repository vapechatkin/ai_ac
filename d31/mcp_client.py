"""Small stdio client for the local Git MCP server."""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


SERVER_FILE = Path(__file__).resolve().with_name("mcp_server.py")


class GitMCPClient:
    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "GitMCPClient":
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_FILE)],
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("MCP-клиент не подключён")
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            text = "\n".join(
                getattr(block, "text", str(block)) for block in result.content
            )
            raise RuntimeError(text or f"MCP tool {name} завершился ошибкой")

        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            # FastMCP wraps a structured return value in `result` on some releases.
            nested = structured.get("result")
            return nested if isinstance(nested, dict) else structured

        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                decoded = json.loads(text)
                if isinstance(decoded, dict):
                    return decoded
        raise RuntimeError(f"MCP tool {name} вернул неизвестный формат")

    async def connect_repository(self, repo_url: str, project_id: str) -> dict[str, Any]:
        return await self._call(
            "connect_repository",
            {"repo_url": repo_url, "project_id": project_id},
        )

    async def branch(self, project_id: str) -> str:
        result = await self._call("git_branch", {"project_id": project_id})
        return str(result["branch"])

    async def commit(self, project_id: str) -> str:
        result = await self._call("git_commit", {"project_id": project_id})
        return str(result["commit"])

    async def files(self, project_id: str, limit: int = 200) -> dict[str, Any]:
        return await self._call(
            "list_files", {"project_id": project_id, "limit": limit}
        )
