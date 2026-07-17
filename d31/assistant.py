#!/usr/bin/env python3
"""CLI entry point: Git URL -> MCP -> persistent RAG -> /help."""

from __future__ import annotations

import argparse
import asyncio
import shlex
import sys
from pathlib import Path

from claude_client import ClaudeProjectClient
from mcp_client import GitMCPClient
from project_store import (
    load_last_project,
    normalize_repo_url,
    project_id_for,
    rag_dir,
    repo_dir,
    save_last_project,
)
from rag import PersistentRAG, format_context


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI-ассистент разработчика с MCP, RAG и Claude",
    )
    parser.add_argument(
        "repository",
        nargs="?",
        help="HTTPS или SSH URL Git-репозитория; без URL откроется последний проект",
    )
    return parser.parse_args()


def parse_help_question(line: str) -> str | None:
    stripped = line.strip()
    if stripped == "/help":
        return ""
    if not stripped.startswith("/help "):
        return None
    raw = stripped[len("/help ") :].strip()
    if not raw:
        return ""
    try:
        parts = shlex.split(raw)
    except ValueError:
        return raw
    return " ".join(parts)


def resolve_repository(argument: str | None) -> tuple[str, str]:
    if argument:
        url = normalize_repo_url(argument)
        return url, project_id_for(url)
    previous = load_last_project()
    if previous is None:
        raise ValueError(
            "При первом запуске передайте Git URL:\n"
            "  python assistant.py https://github.com/user/project.git"
        )
    return previous.repo_url, previous.project_id


async def run() -> int:
    args = parse_args()
    try:
        repository_url, project_id = resolve_repository(args.repository)
    except ValueError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2

    print("Подключаю проект через MCP…")
    try:
        async with GitMCPClient() as mcp:
            connection = await mcp.connect_repository(repository_url, project_id)
            # Explicit MCP calls make Git context independent from clone response.
            branch = await mcp.branch(project_id)
            commit = await mcp.commit(project_id)
    except Exception as exc:
        print(f"Не удалось подключить Git-репозиторий через MCP: {exc}", file=sys.stderr)
        return 1

    save_last_project(repository_url, project_id)
    sync_error = connection.get("sync_error")
    if sync_error:
        print(f"Предупреждение: remote недоступен, используется кэш: {sync_error}")

    rag = PersistentRAG(rag_dir(project_id))
    try:
        status = await asyncio.to_thread(rag.ensure, repo_dir(project_id), commit)
    except Exception as exc:
        print(f"Не удалось подготовить RAG: {exc}", file=sys.stderr)
        return 1

    action = "загружен из кэша" if status.reused else "построен"
    print(
        f"Проект подключён: {repository_url}\n"
        f"Ветка: {branch} · commit: {commit[:12]}\n"
        f"RAG {action}: {status.files} файлов, {status.chunks} фрагментов\n"
        'Введите /help "вопрос по проекту" или /exit.'
    )

    claude = ClaudeProjectClient()
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            return 0

        if not line:
            continue
        if line == "/exit":
            print("До встречи!")
            return 0

        question = parse_help_question(line)
        if question is None:
            print('Доступны только /help "вопрос" и /exit.')
            continue
        if not question:
            print('Использование: /help "Как устроен сервер проекта?"')
            continue

        results = rag.search(question, top_k=6)
        if not results:
            print("В документации не нашлось контекста для этого вопроса.")
            continue
        context = format_context(results)
        try:
            answer = await asyncio.to_thread(
                claude.answer,
                question=question,
                repository_url=repository_url,
                branch=branch,
                commit=commit,
                rag_context=context,
            )
        except Exception as exc:
            print(f"Ошибка Claude API: {exc}")
            continue

        print(f"\n{answer}\n")
        citations = list(dict.fromkeys(result.chunk.citation for result in results))
        print("Контекст RAG: " + ", ".join(citations) + "\n")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
