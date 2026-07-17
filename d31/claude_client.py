"""Grounded Claude response generation for project questions."""

from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """Ты — ассистент разработчика, отвечающий на вопросы о подключённом проекте.

Правила:
1. Отвечай на языке вопроса.
2. Используй только переданную документацию и Git-контекст. Не выдумывай факты.
3. Если контекста недостаточно, прямо скажи, чего именно в документации нет.
4. Для технических утверждений указывай ссылки вида [путь:начальная-строка-конечная-строка].
5. Различай реализованное поведение и планы, если документы содержат оба варианта.
6. Пиши компактно и по существу."""


class ClaudeProjectClient:
    def __init__(self) -> None:
        from dotenv import load_dotenv

        load_dotenv(BASE_DIR / ".env")
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.model = os.getenv("CLAUDE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise RuntimeError(
                "Не задан ANTHROPIC_API_KEY. Скопируйте .env.example в .env "
                "и добавьте API-ключ."
            )
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self.api_key, timeout=60.0, max_retries=2)
        return self._client

    def answer(
        self,
        *,
        question: str,
        repository_url: str,
        branch: str,
        commit: str,
        rag_context: str,
    ) -> str:
        prompt = f"""<project>
repository: {repository_url}
branch: {branch}
commit: {commit}
</project>

<documentation>
{rag_context}
</documentation>

<question>
{question}
</question>"""
        message = self._get_client().messages.create(
            model=self.model,
            max_tokens=1_000,
            temperature=0.1,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        blocks = [block.text for block in message.content if block.type == "text"]
        answer = "\n".join(blocks).strip()
        if not answer:
            raise RuntimeError("Claude вернул пустой ответ")
        return answer
