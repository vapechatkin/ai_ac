"""
Демонстрация подсчёта токенов в диалоге с Claude Haiku 4.5.

Три режима:
  1. short   — короткий диалог (2–3 хода)
  2. long    — длинный диалог (накопление истории)
  3. overflow — диалог с намеренно маленьким лимитом (показывает переполнение)
  4. chat    — интерактивный режим

Запуск:
  python main.py short
  python main.py long
  python main.py overflow
  python main.py chat
"""

import sys

from agent import Agent


# ------------------------------------------------------------------ scenarios


def run_short_dialog() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 1: КОРОТКИЙ ДИАЛОГ")
    print("Наблюдаем, как токены минимальны при малой истории.")
    print("=" * 60 + "\n")

    agent = Agent()
    agent.reset_history()

    pairs = [
        "Как дела?",
        "Сколько планет в Солнечной системе?",
    ]
    for msg in pairs:
        print(f"Вы: {msg}")
        answer = agent.ask(msg)
        print(f"Агент: {answer}\n")


def run_long_dialog() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 2: ДЛИННЫЙ ДИАЛОГ")
    print("Наблюдаем, как токены и стоимость растут с каждым ходом.")
    print("=" * 60 + "\n")

    agent = Agent()
    agent.reset_history()

    questions = [
        "Что такое нейронная сеть?",
        "Как она обучается?",
        "Что такое backpropagation?",
        "Приведи пример функции потерь.",
        "Как бороться с переобучением?",
        "Что такое dropout?",
        "Объясни batch normalization.",
    ]
    for msg in questions:
        print(f"Вы: {msg}")
        answer = agent.ask(msg)
        print(f"Агент: {answer}\n")


def run_overflow_dialog() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 3: РЕАЛЬНОЕ ПЕРЕПОЛНЕНИЕ КОНТЕКСТА")
    print("Набиваем историю ~210 000 токенами и отправляем в API.")
    print("Лимит claude-haiku-4-5 = 200 000 токенов.")
    print("=" * 60 + "\n")

    import anthropic as _anthropic

    agent = Agent()
    agent.reset_history()

    # --- Шаг 1: нормальный короткий ход для разогрева ---
    print("ШАГ 1 — обычный запрос (в пределах лимита):")
    print("Вы: Привет! Как дела?")
    answer = agent.ask("Привет! Как дела?")
    print(f"Агент: {answer}\n")

    # --- Шаг 2: набиваем контекст огромным текстом ---
    # ~4 символа на токен. Хотим ~210 000 токенов.
    # Но у нас уже есть system (~20 tok) + история (~100 tok).
    # Нужно добавить ещё ~210 000 - 120 = ~209 880 токенов текстом.
    # "слово " = 6 символов ≈ 1.5-2 токена (русский).
    # Берём с запасом: 210 000 / 1.5 * 6 = ~840 000 символов.
    FILLER_WORDS = 140_000  # «слово » × 140 000 ≈ 210 000+ токенов
    big_text = "слово " * FILLER_WORDS

    print("ШАГ 2 — строим сообщение с огромным текстом...")
    print(f"  Размер текста: {len(big_text):,} символов ({FILLER_WORDS:,} слов)\n")

    overflow_messages = [
        {"role": "user", "content": f"Вот очень длинный текст:\n\n{big_text}\n\nПодведи итог одним словом."},
    ]

    # --- Шаг 3: count_tokens + реальный запрос → ловим ошибку ---
    print("ШАГ 3 — проверяем токены и отправляем:")
    try:
        agent.ask_raw(overflow_messages)
        print("  [запрос прошёл — контекст не переполнен]")
    except _anthropic.BadRequestError as e:
        print(f"\n💥 РЕАЛЬНАЯ ОШИБКА API:")
        print(f"   Тип:    {type(e).__name__}")
        print(f"   Статус: {e.status_code}")
        # Извлекаем тип ошибки из тела
        body = e.body or {}
        err = body.get("error", {}) if isinstance(body, dict) else {}
        print(f"   Код:    {err.get('type', '—')}")
        print(f"   Текст:  {err.get('message', str(e))}")
        print("\n  Именно это происходит в продакшене без защиты контекста.")
        print("  Решения: компрессия истории, sliding window, summarization.")


def run_chat() -> None:
    print("=" * 60)
    print("ИНТЕРАКТИВНЫЙ РЕЖИМ (claude-haiku-4-5)")
    print("Команды: 'exit' — выход, 'reset' — очистить историю")
    print("=" * 60 + "\n")

    agent = Agent()

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nЗавершение.")
            break

        if not user_input:
            continue
        if user_input.lower() == "exit":
            print("Завершение программы.")
            break
        if user_input.lower() == "reset":
            agent.reset_history()
            continue

        try:
            answer = agent.ask(user_input)
            print(f"Агент: {answer}\n")
        except Exception as e:
            print(f"Ошибка: {e}\n")


# ------------------------------------------------------------------ entry point


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"

    dispatch = {
        "short": run_short_dialog,
        "long": run_long_dialog,
        "overflow": run_overflow_dialog,
        "chat": run_chat,
    }

    if mode not in dispatch:
        print(f"Неизвестный режим: {mode}")
        print(f"Доступны: {', '.join(dispatch)}")
        sys.exit(1)

    dispatch[mode]()


if __name__ == "__main__":
    main()
