# agent.py

import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

# Поддерживаем оба имени переменной
_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

MODEL = "claude-haiku-4-5"
# Цены claude-haiku-4-5: $1.00 / $5.00 за 1M токенов
PRICE_INPUT_PER_TOKEN = 1.00 / 1_000_000
PRICE_OUTPUT_PER_TOKEN = 5.00 / 1_000_000

SYSTEM_PROMPT = "Ты полезный AI-ассистент. Отвечай кратко и по делу."

# Лимит контекста модели (200K для Haiku 4.5).
# Для демонстрации переполнения установим маленький порог.
DEMO_OVERFLOW_THRESHOLD = 500  # токенов — намеренно мал для демо


class Agent:
    def __init__(self, overflow_demo: bool = False):
        self.client = anthropic.Anthropic(api_key=_api_key)
        self.history_file = "history.json"
        self.messages: list[dict] = self._load_history()

        # Накопленная статистика за сессию
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.turn_number = 0

        # Если True — имитируем жёсткий лимит для демо переполнения
        self.overflow_demo = overflow_demo
        self.token_limit = DEMO_OVERFLOW_THRESHOLD if overflow_demo else 200_000

    # ------------------------------------------------------------------ history

    def _load_history(self) -> list[dict]:
        if os.path.exists(self.history_file):
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_history(self) -> None:
        with open(self.history_file, "w", encoding="utf-8") as f:
            json.dump(self.messages, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ token counting

    def _count_tokens(self, messages: list[dict]) -> int:
        """Считает токены для переданного набора сообщений через API."""
        response = self.client.messages.count_tokens(
            model=MODEL,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        return response.input_tokens

    def _count_single_message(self, role: str, content: str) -> int:
        """Считает токены одного изолированного сообщения."""
        return self._count_tokens([{"role": role, "content": content}])

    # ------------------------------------------------------------------ display

    def _print_token_stats(
        self,
        tokens_current_msg: int,
        tokens_full_history: int,
        tokens_response: int,
        turn_total_input: int,
        turn_total_output: int,
    ) -> None:
        input_cost = turn_total_input * PRICE_INPUT_PER_TOKEN
        output_cost = tokens_response * PRICE_OUTPUT_PER_TOKEN
        session_cost = (
            self.session_input_tokens * PRICE_INPUT_PER_TOKEN
            + self.session_output_tokens * PRICE_OUTPUT_PER_TOKEN
        )

        print("\n" + "=" * 54)
        print(f"  СТАТИСТИКА ТОКЕНОВ  (ход #{self.turn_number})")
        print("=" * 54)
        print(f"  Текущее сообщение (изолировано): {tokens_current_msg:>8} tok")
        print(f"  Вся история (входящий контекст): {tokens_full_history:>8} tok")
        print(f"  Ответ модели:                    {tokens_response:>8} tok")
        print("-" * 54)
        print(f"  Итого этот ход (вход):           {turn_total_input:>8} tok")
        print(f"  Итого этот ход (выход):          {turn_total_output:>8} tok")
        print("-" * 54)
        print(f"  Накопленный вход за сессию:      {self.session_input_tokens:>8} tok")
        print(f"  Накопленный выход за сессию:     {self.session_output_tokens:>8} tok")
        print("-" * 54)
        cost_line = f"  Стоимость этого хода:           ${input_cost + output_cost:.6f}"
        print(cost_line)
        print(f"  Стоимость сессии (нарастающая): ${session_cost:.6f}")
        if self.overflow_demo:
            pct = tokens_full_history / self.token_limit * 100
            bar_len = 30
            filled = int(bar_len * min(pct, 100) / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            print(f"\n  Лимит-демо [{bar}] {pct:.0f}%")
            print(f"  {tokens_full_history} / {self.token_limit} токенов")
        print("=" * 54 + "\n")

    # ------------------------------------------------------------------ ask

    def ask(self, user_message: str) -> str:
        self.turn_number += 1

        # 1. Считаем токены текущего сообщения (изолировано)
        tokens_current = self._count_single_message("user", user_message)

        # 2. Добавляем сообщение в историю и считаем токены всей истории
        self.messages.append({"role": "user", "content": user_message})
        tokens_history = self._count_tokens(self.messages)

        # 3. Проверяем лимит (для демо переполнения)
        if self.overflow_demo and tokens_history > self.token_limit:
            print(
                f"\n⚠️  ПЕРЕПОЛНЕНИЕ! История ({tokens_history} tok) "
                f"превышает лимит ({self.token_limit} tok).\n"
                f"   Модель получила бы ошибку context_length_exceeded.\n"
                f"   В реальных системах здесь нужна компрессия или сброс истории.\n"
            )
            # Откатываем сообщение, чтобы не испортить историю
            self.messages.pop()
            return "[OVERFLOW] Контекст переполнен. История сброшена."

        # 4. Отправляем запрос к модели
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=self.messages,
        )

        assistant_text = response.content[0].text
        turn_input = response.usage.input_tokens
        turn_output = response.usage.output_tokens

        # 5. Обновляем накопленные счётчики
        self.session_input_tokens += turn_input
        self.session_output_tokens += turn_output

        # 6. Сохраняем ответ в историю
        self.messages.append({"role": "assistant", "content": assistant_text})
        self._save_history()

        # 7. Печатаем статистику
        self._print_token_stats(
            tokens_current_msg=tokens_current,
            tokens_full_history=tokens_history,
            tokens_response=turn_output,
            turn_total_input=turn_input,
            turn_total_output=turn_output,
        )

        return assistant_text

    def ask_raw(self, messages: list[dict]) -> None:
        """
        Отправляет произвольный список сообщений напрямую в API
        без каких-либо проверок — для демонстрации реального переполнения.
        """
        tokens = self._count_tokens(messages)
        print(f"\n  Подсчёт токенов перед отправкой: {tokens:,} tok")
        print(f"  Лимит контекста claude-haiku-4-5:  200,000 tok")
        pct = tokens / 200_000 * 100
        bar_len = 40
        filled = int(bar_len * min(pct, 100) / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {pct:.0f}%\n")

        print("  Отправляем запрос к API...")
        self.client.messages.create(
            model=MODEL,
            max_tokens=16,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

    def reset_history(self) -> None:
        """Очищает историю диалога."""
        self.messages = []
        if os.path.exists(self.history_file):
            os.remove(self.history_file)
        self.session_input_tokens = 0
        self.session_output_tokens = 0
        self.turn_number = 0
        print("История диалога очищена.\n")
