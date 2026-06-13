# agent.py
#
# Агент с тремя стратегиями управления контекстом:
#
#   "window"   — Sliding Window: только последние N сообщений
#   "facts"    — Sticky Facts: facts (key-value) + последние N сообщений
#   "branching"— Branching: ветки диалога от checkpoint'а
#
# Общий интерфейс: agent.ask(text) → (answer, stats)

import json
import os
from copy import deepcopy
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

MODEL         = "claude-haiku-4-5"
PRICE_IN      = 1.00 / 1_000_000
PRICE_OUT     = 5.00 / 1_000_000
WINDOW_SIZE   = 6   # сообщений в скользящем окне

SYSTEM_BASE = "Ты полезный AI-ассистент. Помни контекст разговора. Отвечай кратко."

FACTS_EXTRACTION_PROMPT = """\
Из сообщения пользователя извлеки важные факты для сохранения в памяти.
Верни JSON-объект с произвольными ключами на русском языке.
Если в сообщении нет новых фактов — верни пустой объект {}.
Примеры ключей: "цель", "язык", "БД", "ограничения", "решение", "имя".
Отвечай ТОЛЬКО валидным JSON, без пояснений."""


# ─────────────────────────────────────────── базовый агент

class Agent:
    def __init__(self, strategy: str, name: str = ""):
        assert strategy in ("window", "facts", "branching"), \
            "strategy must be 'window', 'facts', or 'branching'"

        self.strategy = strategy
        self.name     = name or strategy.upper()
        self.client   = anthropic.Anthropic(api_key=_api_key)

        # Общая полная история (для сравнения token_full)
        self.full_history: list[dict] = []

        # Strategy: facts
        self.facts: dict[str, Any] = {}

        # Strategy: branching
        self.branches: dict[str, list[dict]] = {"main": []}
        self.current_branch: str             = "main"
        self._checkpoint_snapshot: list[dict] | None = None

        # Счётчики
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self.turn_count          = 0

    # ─────────────────────── branching helpers

    def checkpoint(self) -> None:
        """Сохраняет текущее состояние ветки как точку ветвления."""
        self._checkpoint_snapshot = deepcopy(
            self.branches[self.current_branch]
        )
        print(f"  [checkpoint] сохранён в ветке «{self.current_branch}» "
              f"({len(self._checkpoint_snapshot)} сообщений)")

    def branch(self, name: str) -> None:
        """Создаёт новую ветку от последнего checkpoint."""
        if self._checkpoint_snapshot is None:
            raise RuntimeError("Сначала вызови checkpoint()")
        self.branches[name] = deepcopy(self._checkpoint_snapshot)
        self.current_branch  = name
        print(f"  [branch] создана ветка «{name}» от checkpoint "
              f"({len(self.branches[name])} сообщений)")

    def switch(self, name: str) -> None:
        """Переключается на существующую ветку."""
        if name not in self.branches:
            raise KeyError(f"Ветка «{name}» не существует")
        self.current_branch = name
        print(f"  [switch] переключились на ветку «{name}» "
              f"({len(self.branches[name])} сообщений)")

    def list_branches(self) -> list[str]:
        return list(self.branches)

    # ─────────────────────── facts helpers

    def _extract_facts(self, user_message: str) -> None:
        """Просит модель выделить факты из сообщения и мержит в self.facts."""
        try:
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=200,
                system=FACTS_EXTRACTION_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = resp.content[0].text.strip()
            new_facts = json.loads(raw)
            if isinstance(new_facts, dict):
                self.facts.update(new_facts)
        except (json.JSONDecodeError, Exception):
            pass  # не критично, продолжаем без новых фактов

    def _facts_block(self) -> str:
        if not self.facts:
            return ""
        lines = "\n".join(f"  {k}: {v}" for k, v in self.facts.items())
        return f"[ЗАПОМНЕННЫЕ ФАКТЫ]\n{lines}"

    # ─────────────────────── context builders

    def _build_context(self) -> list[dict]:
        if self.strategy == "window":
            return self.full_history[-WINDOW_SIZE:]

        if self.strategy == "facts":
            recent  = self.full_history[-WINDOW_SIZE:]
            fb = self._facts_block()
            if not fb:
                return recent
            return [
                {"role": "user",      "content": fb},
                {"role": "assistant", "content": "Понял, учту эти факты."},
            ] + recent

        if self.strategy == "branching":
            return self.branches[self.current_branch][-WINDOW_SIZE:]

        return self.full_history  # fallback

    def _system_prompt(self) -> str:
        return SYSTEM_BASE

    # ─────────────────────── token counting

    def _count_tokens(self, messages: list[dict]) -> int:
        r = self.client.messages.count_tokens(
            model=MODEL,
            system=self._system_prompt(),
            messages=messages,
        )
        return r.input_tokens

    # ─────────────────────── ask

    def ask(self, user_message: str) -> tuple[str, dict]:
        self.turn_count += 1

        # Обновляем общую историю
        self.full_history.append({"role": "user", "content": user_message})

        # Для branching — пишем в текущую ветку
        if self.strategy == "branching":
            self.branches[self.current_branch].append(
                {"role": "user", "content": user_message}
            )

        # Для facts — извлекаем факты (доп. вызов API)
        if self.strategy == "facts":
            self._extract_facts(user_message)

        # Строим контекст для запроса
        context = self._build_context()

        # Считаем токены
        tokens_full    = self._count_tokens(self.full_history)
        tokens_context = self._count_tokens(context)

        # Основной запрос
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=self._system_prompt(),
            messages=context,
        )

        answer     = response.content[0].text.strip()
        inp_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens

        self.total_input_tokens  += inp_tokens
        self.total_output_tokens += out_tokens

        # Записываем ответ в историю
        self.full_history.append({"role": "assistant", "content": answer})
        if self.strategy == "branching":
            self.branches[self.current_branch].append(
                {"role": "assistant", "content": answer}
            )

        stats = {
            "turn":         self.turn_count,
            "branch":       self.current_branch if self.strategy == "branching" else None,
            "tokens_full":  tokens_full,
            "tokens_sent":  tokens_context,
            "tokens_saved": tokens_full - tokens_context,
            "facts_count":  len(self.facts),
            "session_in":   self.total_input_tokens,
            "session_out":  self.total_output_tokens,
            "session_cost": (
                self.total_input_tokens  * PRICE_IN +
                self.total_output_tokens * PRICE_OUT
            ),
        }
        return answer, stats
