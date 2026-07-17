"""Long-lived stdio client for the d33 CRM MCP server."""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


BASE_DIR = Path(__file__).resolve().parent
SERVER_FILE = BASE_DIR / "crm_mcp_server.py"


@dataclass(frozen=True)
class CRMContext:
    user: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None

    @property
    def user_id(self) -> str | None:
        return str(self.user["id"]) if self.user else None

    @property
    def ticket_id(self) -> str | None:
        return str(self.ticket["id"]) if self.ticket else None


class CRMClient:
    def __init__(self, crm_file: Path | None = None) -> None:
        self.crm_file = (crm_file or BASE_DIR / "data" / "crm.json").resolve()
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "CRMClient":
        environment = dict(os.environ)
        environment["D33_CRM_FILE"] = str(self.crm_file)
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(SERVER_FILE)],
            env=environment,
        )
        read, write = await self._stack.enter_async_context(stdio_client(parameters))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._stack.aclose()

    async def resolve_context(
        self, ticket_id: str | None = None, user_id: str | None = None
    ) -> CRMContext:
        if ticket_id:
            result = await self._call(
                "get_ticket_context", {"ticket_id": ticket_id}
            )
            if not result.get("found") or not isinstance(result.get("context"), dict):
                raise LookupError(f"Тикет не найден: {ticket_id}")
            context = result["context"]
            ticket = context.get("ticket")
            user = context.get("user")
            if not isinstance(ticket, dict) or not isinstance(user, dict):
                raise RuntimeError("MCP вернул повреждённый контекст тикета")
            if user_id and user.get("id") != user_id:
                raise ValueError("Тикет принадлежит другому пользователю")
            return CRMContext(user=user, ticket=ticket)

        if user_id:
            result = await self._call("get_user", {"user_id": user_id})
            user = result.get("user")
            if not result.get("found") or not isinstance(user, dict):
                raise LookupError(f"Пользователь не найден: {user_id}")
            return CRMContext(user=user)
        return CRMContext()

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self._session is None:
            raise RuntimeError("CRM MCP client не подключён")
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            message = "\n".join(
                getattr(block, "text", str(block)) for block in result.content
            )
            raise RuntimeError(message or f"MCP tool {name} завершился ошибкой")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            nested = structured.get("result")
            return nested if isinstance(nested, dict) else structured
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                decoded = json.loads(text)
                if isinstance(decoded, dict):
                    return decoded
        raise RuntimeError(f"MCP tool {name} вернул неизвестный формат")
