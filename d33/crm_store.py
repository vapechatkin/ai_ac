"""Read-only JSON CRM storage used behind the MCP boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CRMStore:
    def __init__(self, path: Path) -> None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Не удалось загрузить CRM JSON: {exc}") from exc
        users = raw.get("users")
        tickets = raw.get("tickets")
        if not isinstance(users, list) or not isinstance(tickets, list):
            raise ValueError("CRM JSON должен содержать массивы users и tickets")
        self.users = _index_records(users, "users")
        self.tickets = _index_records(tickets, "tickets")
        for ticket in self.tickets.values():
            if ticket.get("user_id") not in self.users:
                raise ValueError(
                    f"Тикет {ticket['id']} ссылается на неизвестного пользователя"
                )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        user = self.users.get(user_id)
        return dict(user) if user is not None else None

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        ticket = self.tickets.get(ticket_id.upper())
        return dict(ticket) if ticket is not None else None

    def get_ticket_context(self, ticket_id: str) -> dict[str, Any] | None:
        ticket = self.get_ticket(ticket_id)
        if ticket is None:
            return None
        user = self.get_user(str(ticket["user_id"]))
        return {"ticket": ticket, "user": user}

    def list_user_tickets(
        self, user_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        return [
            dict(ticket)
            for ticket in self.tickets.values()
            if ticket.get("user_id") == user_id
            and (status is None or ticket.get("status") == status)
        ]


def _index_records(records: list[Any], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError(f"Каждая запись {label} должна иметь строковый id")
        key = record["id"].upper() if label == "tickets" else record["id"]
        if key in indexed:
            raise ValueError(f"Дублирующийся id в {label}: {record['id']}")
        indexed[key] = dict(record)
    return indexed
