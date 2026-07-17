"""stdio MCP server exposing the JSON CRM as read-only tools."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from crm_store import CRMStore


BASE_DIR = Path(__file__).resolve().parent
CRM_FILE = Path(os.getenv("D33_CRM_FILE", str(BASE_DIR / "data" / "crm.json")))
store = CRMStore(CRM_FILE)

mcp = FastMCP(
    "d33 JSON CRM",
    instructions="Read users and support tickets from the configured JSON CRM.",
    json_response=True,
    log_level="ERROR",
)


@mcp.tool()
def get_user(user_id: str) -> dict[str, Any]:
    """Return a user by CRM id."""
    user = store.get_user(user_id)
    return {"found": user is not None, "user": user}


@mcp.tool()
def get_ticket(ticket_id: str) -> dict[str, Any]:
    """Return a support ticket by id."""
    ticket = store.get_ticket(ticket_id)
    return {"found": ticket is not None, "ticket": ticket}


@mcp.tool()
def get_ticket_context(ticket_id: str) -> dict[str, Any]:
    """Return a ticket together with its linked user."""
    context = store.get_ticket_context(ticket_id)
    return {"found": context is not None, "context": context}


@mcp.tool()
def list_user_tickets(user_id: str, status: str | None = None) -> dict[str, Any]:
    """Return tickets for a user, optionally filtered by status."""
    tickets = store.list_user_tickets(user_id, status=status)
    return {"tickets": tickets, "total": len(tickets)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
