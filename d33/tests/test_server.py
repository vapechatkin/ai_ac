from pathlib import Path

from fastapi.testclient import TestClient

from rag import KnowledgeRAG
from server import create_app
from support import SupportResult


BASE_DIR = Path(__file__).resolve().parents[1]


class FakeEngine:
    def __init__(self) -> None:
        self.rag = KnowledgeRAG.from_directory(BASE_DIR / "knowledge")

    async def answer(
        self,
        question: str,
        ticket_id: str | None = None,
        user_id: str | None = None,
    ) -> SupportResult:
        if ticket_id == "missing":
            raise LookupError("Тикет не найден: missing")
        return SupportResult(
            answer=f"Ответ на: {question}",
            sources=("faq.md:1-10",),
            ticket_id=ticket_id,
            user_id=user_id,
            model="fake-model",
        )


def test_support_endpoint_and_health() -> None:
    with TestClient(create_app(FakeEngine())) as client:
        health = client.get("/health")
        response = client.post(
            "/support",
            json={"question": "Почему не работает авторизация?", "ticket_id": "TCK-101"},
        )

    assert health.status_code == 200
    assert health.json()["crm_transport"] == "MCP stdio"
    assert response.status_code == 200
    assert response.json()["ticket_id"] == "TCK-101"
    assert response.json()["sources"] == ["faq.md:1-10"]


def test_unknown_ticket_returns_404() -> None:
    with TestClient(create_app(FakeEngine())) as client:
        response = client.post(
            "/support",
            json={"question": "Что случилось?", "ticket_id": "missing"},
        )

    assert response.status_code == 404
