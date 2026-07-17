from pathlib import Path

from rag import KnowledgeRAG


BASE_DIR = Path(__file__).resolve().parents[1]


def test_auth_question_retrieves_reinstall_guidance() -> None:
    rag = KnowledgeRAG.from_directory(BASE_DIR / "knowledge")

    results = rag.search(
        "unauthorized авторизация после переустановки пропал гостевой профиль"
    )

    assert results
    combined = "\n".join(result.chunk.text for result in results)
    assert "deviceKey" in combined
    assert any(result.chunk.path == "faq.md" for result in results)


def test_room_protocol_question_retrieves_version_advice() -> None:
    rag = KnowledgeRAG.from_directory(BASE_DIR / "knowledge")

    results = rag.search("protocol_mismatch старая web версия войти в комнату")

    assert results
    assert "обнов" in "\n".join(result.chunk.text.lower() for result in results)
