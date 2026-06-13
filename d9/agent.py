# agent.py
#
# Агент с компрессией истории.
#
# Логика окна контекста:
#   - Последние RECENT_WINDOW сообщений хранятся дословно.
#   - Всё, что старше — сжимается в одно summary каждые SUMMARY_EVERY сообщений.
#   - В запрос к модели подаётся: [summary-блок] + [последние N сообщений].

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

MODEL = "claude-haiku-4-5"
PRICE_IN  = 1.00 / 1_000_000   # $1 за 1M входящих токенов
PRICE_OUT = 5.00 / 1_000_000   # $5 за 1M выходящих токенов

SYSTEM_PROMPT = (
    "Ты полезный AI-ассистент. Помни контекст разговора. Отвечай кратко."
)

RECENT_WINDOW  = 4   # сколько последних сообщений хранить дословно
SUMMARY_EVERY  = 6   # сжимать каждые N накопившихся сообщений вне окна


class Agent:
    """
    Агент с двумя режимами работы.

    compress=False  — полная история без изменений (базовый режим)
    compress=True   — компрессия: summary + последние RECENT_WINDOW сообщений
    """

    def __init__(self, compress: bool = False, name: str = ""):
        self.client   = anthropic.Anthropic(api_key=_api_key)
        self.compress = compress
        self.name     = name or ("СЖАТЫЙ" if compress else "ПОЛНЫЙ")

        # Полная история (всегда хранится для сравнения)
        self.full_history: list[dict] = []

        # Summary накопленных старых сообщений (только для compress=True)
        self.summary: str = ""

        # Статистика
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self.turn_count          = 0

    # ------------------------------------------------------------------ summary

    def _make_summary(self, messages: list[dict]) -> str:
        """Просит модель кратко пересказать переданный список сообщений."""
        text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        resp = self.client.messages.create(
            model=MODEL,
            max_tokens=300,
            system="Ты ассистент, который делает краткое резюме диалога.",
            messages=[{
                "role": "user",
                "content": (
                    "Сделай краткое резюме следующего диалога на русском языке. "
                    "Сохрани ключевые факты и договорённости. Максимум 5 предложений.\n\n"
                    + text
                ),
            }],
        )
        return resp.content[0].text.strip()

    # ------------------------------------------------------------------ context builder

    def _build_context(self) -> list[dict]:
        """
        Формирует список сообщений для отправки в API.

        compress=False → вся full_history
        compress=True  → summary (как user-сообщение) + последние RECENT_WINDOW
        """
        if not self.compress:
            return list(self.full_history)

        recent = self.full_history[-RECENT_WINDOW:] if self.full_history else []

        if not self.summary:
            return recent

        # Summary оборачиваем в пару user/assistant, чтобы не нарушать чередование
        summary_block = [
            {
                "role": "user",
                "content": f"[КРАТКОЕ РЕЗЮМЕ предыдущего диалога]:\n{self.summary}",
            },
            {
                "role": "assistant",
                "content": "Понял, учту контекст из резюме.",
            },
        ]
        return summary_block + recent

    def _maybe_compress(self) -> None:
        """
        Если сообщений вне окна накопилось >= SUMMARY_EVERY — сжимаем их.
        Вызывается после каждого хода.
        """
        if not self.compress:
            return

        outside_window = len(self.full_history) - RECENT_WINDOW
        if outside_window < SUMMARY_EVERY:
            return

        # Берём все сообщения вне окна
        to_summarize = self.full_history[:outside_window]

        print(f"    ↳ [компрессия] сжимаем {len(to_summarize)} сообщений в summary...")
        new_summary = self._make_summary(to_summarize)

        # Если summary уже было — объединяем
        if self.summary:
            combined_text = (
                f"Предыдущее резюме:\n{self.summary}\n\n"
                f"Дополнение:\n{new_summary}"
            )
            self.summary = self._make_summary([
                {"role": "user", "content": combined_text}
            ])
        else:
            self.summary = new_summary

        # Удаляем сжатые сообщения из истории
        self.full_history = self.full_history[outside_window:]
        print(f"    ↳ [компрессия] готово. Summary: {len(self.summary)} симв.\n")

    # ------------------------------------------------------------------ token counting

    def _count_tokens(self, messages: list[dict]) -> int:
        resp = self.client.messages.count_tokens(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return resp.input_tokens

    # ------------------------------------------------------------------ ask

    def ask(self, user_message: str) -> tuple[str, dict]:
        """
        Отправляет сообщение, возвращает (ответ, статистика).
        Статистика содержит числа токенов для обоих режимов сравнения.
        """
        self.turn_count += 1
        self.full_history.append({"role": "user", "content": user_message})

        # Контекст, который реально пойдёт в запрос
        context = self._build_context()

        # Считаем токены до отправки
        tokens_full    = self._count_tokens(list(self.full_history))
        tokens_context = self._count_tokens(context)

        # Запрос к модели
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=context,
        )

        answer     = response.content[0].text.strip()
        inp_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens

        self.total_input_tokens  += inp_tokens
        self.total_output_tokens += out_tokens

        self.full_history.append({"role": "assistant", "content": answer})

        # Компрессия (если нужна) после записи ответа
        self._maybe_compress()

        stats = {
            "turn":            self.turn_count,
            "tokens_full":     tokens_full,
            "tokens_sent":     tokens_context,
            "tokens_saved":    tokens_full - tokens_context,
            "out_tokens":      out_tokens,
            "session_in":      self.total_input_tokens,
            "session_out":     self.total_output_tokens,
            "session_cost":    (
                self.total_input_tokens  * PRICE_IN +
                self.total_output_tokens * PRICE_OUT
            ),
            "summary_len":     len(self.summary),
            "full_msgs":       len(self.full_history),
        }
        return answer, stats
