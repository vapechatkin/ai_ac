import json
from pathlib import Path

from rag import PersistentRAG, RAGIndex, chunk_text, discover_documents


def test_discovery_includes_docs_and_schemas_but_not_source(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Project", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "architecture.md").write_text("# Architecture", encoding="utf-8")
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "openapi.yaml").write_text("openapi: 3.1.0", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('not documentation')", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "README.md").write_text("ignored", encoding="utf-8")

    paths = [path.relative_to(tmp_path).as_posix() for path in discover_documents(tmp_path)]

    assert paths == ["api/openapi.yaml", "docs/architecture.md", "README.md"]


def test_chunking_keeps_source_coordinates() -> None:
    text = "# API\n\nPOST /rooms creates a room.\n"
    chunks = chunk_text(text, "docs/api.md")
    assert chunks[0].path == "docs/api.md"
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 3
    assert chunks[0].heading == "API"


def test_search_ranks_relevant_russian_document(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Запуск\nСервер запускается командой dart run bin/server.dart.",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rules.md").write_text(
        "# Правила\nИгрок бросает кубики и покупает улицы.",
        encoding="utf-8",
    )
    index, _ = RAGIndex.build(tmp_path)

    results = index.search("как запустить сервер")

    assert results
    assert results[0].chunk.path == "README.md"


def test_persistent_index_is_reused_for_same_commit(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "README.md").write_text("# Test\nPersistent RAG index", encoding="utf-8")
    rag = PersistentRAG(tmp_path / "rag")

    first = rag.ensure(repository, "abc123")
    second = PersistentRAG(tmp_path / "rag").ensure(repository, "abc123")

    assert first.reused is False
    assert second.reused is True
    metadata = json.loads((tmp_path / "rag" / "metadata.json").read_text())
    assert metadata["commit"] == "abc123"
