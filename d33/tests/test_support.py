import asyncio
from pathlib import Path

from crm_mcp_client import CRMContext
from rag import KnowledgeRAG
from support import SupportEngine


BASE_DIR = Path(__file__).resolve().parents[1]


class FakeCRM:
    async def resolve_context(
        self, ticket_id: str | None = None, user_id: str | None = None
    ) -> CRMContext:
        assert ticket_id == "TCK-101"
        return CRMContext(
            user={
                "id": "usr_1001",
                "platform": "android",
                "app_version": "0.1.0",
                "account_status": "active",
                "plan": "closed_beta",
            },
            ticket={
                "id": "TCK-101",
                "subject": "Авторизация после переустановки",
                "description": "Сервер отвечает unauthorized",
                "error_code": "unauthorized",
                "tags": ["auth", "reinstall"],
            },
        )


class FakeLLM:
    model = "fake-model"

    def __init__(self) -> None:
        self.knowledge = ""

    def answer(
        self, question: str, crm_context: CRMContext, knowledge_context: str
    ) -> str:
        self.knowledge = knowledge_context
        assert crm_context.ticket_id == "TCK-101"
        return "После переустановки изменился ключ устройства; войдите как новый гость."


def test_engine_combines_ticket_context_and_rag() -> None:
    llm = FakeLLM()
    engine = SupportEngine(
        rag=KnowledgeRAG.from_directory(BASE_DIR / "knowledge"),
        crm=FakeCRM(),
        llm=llm,
    )

    result = asyncio.run(
        engine.answer("Почему не работает авторизация?", ticket_id="TCK-101")
    )

    assert result.ticket_id == "TCK-101"
    assert result.user_id == "usr_1001"
    assert result.model == "fake-model"
    assert result.sources
    assert "deviceKey" in llm.knowledge
