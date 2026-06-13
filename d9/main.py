"""
Демонстрация компрессии истории диалога.

Четыре сценария:
  1. nocompress   — длинный диалог без компрессии (токены растут линейно)
  2. compress     — тот же диалог с компрессией (summary + sliding window)
  3. compare      — оба агента параллельно, пошаговое сравнение токенов
  4. memory_test  — проверка потери нити: вопросы о деталях из начала диалога

Запуск:
  python main.py nocompress
  python main.py compress
  python main.py compare
  python main.py memory_test
"""

import sys
from agent import Agent


DIALOG = [
    "Что такое нейронная сеть?",
    "Как она обучается? Расскажи про градиентный спуск.",
    "Что такое backpropagation?",
    "Зачем нужны функции активации? Приведи примеры.",
    "Объясни dropout и зачем он нужен.",
    "Что такое batch normalization?",
    "Как работает attention-механизм?",
    "Расскажи про архитектуру Transformer.",
    "Чем BERT отличается от GPT?",
    "Какие метрики используют для оценки языковых моделей?",
    "Что такое перплексия (perplexity)?",
    "Как бороться с галлюцинациями в LLM?",
]

BAR_LEN = 40


def bar(value: int, maximum: int, width: int = BAR_LEN) -> str:
    pct = min(value / maximum, 1.0)
    filled = int(width * pct)
    return "█" * filled + "░" * (width - filled)


def print_turn_stats(label: str, stats: dict, max_tokens: int = 6000) -> None:
    s = stats
    print(f"\n  [{label}] ход #{s['turn']}")
    print(f"    Полная история:   {s['tokens_full']:>6} tok")
    if label != "БЕЗ СЖАТИЯ":
        saved = s["tokens_saved"]
        pct   = saved / s["tokens_full"] * 100 if s["tokens_full"] else 0
        print(f"    Отправлено в API: {s['tokens_sent']:>6} tok  (сэкономлено {saved} tok / {pct:.0f}%)")
        if s["summary_len"]:
            print(f"    Summary в памяти: {s['summary_len']} симв.")
    print(f"    [{bar(s['tokens_full'], max_tokens)}] {s['tokens_full']}/{max_tokens}")
    print(f"    Стоимость сессии: ${s['session_cost']:.6f}")


# ------------------------------------------------------------------ scenario 1


def run_nocompress() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 1: БЕЗ КОМПРЕССИИ")
    print("Все сообщения хранятся и отправляются целиком.")
    print("Токены растут с каждым ходом.")
    print("=" * 60)

    agent = Agent(compress=False, name="БЕЗ СЖАТИЯ")

    for msg in DIALOG:
        print(f"\nВы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"Агент: {answer}")
        print_turn_stats("БЕЗ СЖАТИЯ", stats)

    print("\n" + "=" * 60)
    print("ИТОГ (без компрессии)")
    print(f"  Всего ходов:      {agent.turn_count}")
    print(f"  Вход (сессия):    {agent.total_input_tokens:,} tok")
    print(f"  Выход (сессия):   {agent.total_output_tokens:,} tok")
    total_cost = (
        agent.total_input_tokens  * 1e-6 +
        agent.total_output_tokens * 5e-6
    )
    print(f"  Стоимость:        ${total_cost:.5f}")
    print("=" * 60)


# ------------------------------------------------------------------ scenario 2


def run_compress() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 2: С КОМПРЕССИЕЙ")
    print(f"  Окно: последние 4 сообщения дословно.")
    print(f"  Компрессия каждые 6 сообщений вне окна.")
    print("=" * 60)

    agent = Agent(compress=True, name="СО СЖАТИЕМ")

    for msg in DIALOG:
        print(f"\nВы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"Агент: {answer}")
        print_turn_stats("СО СЖАТИЕМ", stats)

    print("\n" + "=" * 60)
    print("ИТОГ (с компрессией)")
    print(f"  Всего ходов:      {agent.turn_count}")
    print(f"  Вход (сессия):    {agent.total_input_tokens:,} tok")
    print(f"  Выход (сессия):   {agent.total_output_tokens:,} tok")
    total_cost = (
        agent.total_input_tokens  * 1e-6 +
        agent.total_output_tokens * 5e-6
    )
    print(f"  Стоимость:        ${total_cost:.5f}")
    print("=" * 60)


# ------------------------------------------------------------------ scenario 3


def run_compare() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 3: СРАВНЕНИЕ — без vs со сжатием")
    print("Оба агента получают одинаковый диалог.")
    print("=" * 60)

    agent_full = Agent(compress=False, name="ПОЛНЫЙ")
    agent_comp = Agent(compress=True,  name="СЖАТЫЙ")

    total_full_tokens = 0
    total_comp_tokens = 0

    for i, msg in enumerate(DIALOG, 1):
        print(f"\n{'─'*60}")
        print(f"  Вопрос #{i}: {msg}")
        print(f"{'─'*60}")

        ans_full, sf = agent_full.ask(msg)
        ans_comp, sc = agent_comp.ask(msg)

        total_full_tokens += sf["tokens_full"]
        total_comp_tokens += sc["tokens_sent"]

        saved     = sf["tokens_full"] - sc["tokens_sent"]
        saved_pct = saved / sf["tokens_full"] * 100 if sf["tokens_full"] else 0

        print(f"\n  [БЕЗ СЖАТИЯ] {ans_full}")
        print(f"  [СО СЖАТИЕМ] {ans_comp}")

        print(f"\n  {'Метрика':<30} {'БЕЗ СЖАТИЯ':>12} {'СО СЖАТИЕМ':>12}")
        print(f"  {'─'*54}")
        print(f"  {'Полная история (tok)':<30} {sf['tokens_full']:>12,} {sc['tokens_full']:>12,}")
        print(f"  {'Отправлено в API (tok)':<30} {sf['tokens_sent']:>12,} {sc['tokens_sent']:>12,}")
        print(f"  {'Экономия токенов':<30} {'—':>12} {saved:>+12,}  ({saved_pct:.0f}%)")
        print(f"  {'Стоимость сессии ($)':<30} {sf['session_cost']:>12.5f} {sc['session_cost']:>12.5f}")
        if sc["summary_len"]:
            print(f"  {'Summary (симв.)':<30} {'—':>12} {sc['summary_len']:>12}")

    print(f"\n{'═'*60}")
    print("ФИНАЛЬНОЕ СРАВНЕНИЕ")
    print(f"{'═'*60}")

    cost_full = (
        agent_full.total_input_tokens  * 1e-6 +
        agent_full.total_output_tokens * 5e-6
    )
    cost_comp = (
        agent_comp.total_input_tokens  * 1e-6 +
        agent_comp.total_output_tokens * 5e-6
    )
    cost_saved = cost_full - cost_comp
    cost_pct   = cost_saved / cost_full * 100 if cost_full else 0

    print(f"  {'':30} {'БЕЗ СЖАТИЯ':>12} {'СО СЖАТИЕМ':>12}")
    print(f"  {'─'*54}")
    print(f"  {'Входящих токенов (всего)':<30} {agent_full.total_input_tokens:>12,} {agent_comp.total_input_tokens:>12,}")
    print(f"  {'Исходящих токенов (всего)':<30} {agent_full.total_output_tokens:>12,} {agent_comp.total_output_tokens:>12,}")
    print(f"  {'Итоговая стоимость ($)':<30} {cost_full:>12.5f} {cost_comp:>12.5f}")
    print(f"  {'Экономия ($)':<30} {'—':>12} {cost_saved:>+12.5f}  ({cost_pct:.0f}%)")
    print(f"{'═'*60}")


# ------------------------------------------------------------------ scenario 4


# Диалог нарочно упоминает конкретные детали, которые позже запрашиваются обратно.
# После компрессии эти детали окажутся в summary — проверяем, сохранились ли они.
MEMORY_SETUP = [
    "Меня зовут Алексей. Запомни это.",
    "Я работаю Python-разработчиком в компании DataFlow. Запомни.",
    "Мой любимый фреймворк — FastAPI. Я использую его уже 3 года.",
    "У меня есть проект: API для анализа тональности текста. Он на FastAPI + Transformers.",
    "Я предпочитаю PostgreSQL, а не MySQL. Принципиально.",
    "Кстати, я пишу тесты только с pytest, никогда с unittest.",
    # после этого хода сработает первая компрессия (6 сообщений вне окна)
    "Расскажи мне в общем про REST API.",
    "А что такое gRPC?",
    "Чем отличается синхронный и асинхронный код в Python?",
]

MEMORY_QUESTIONS = [
    "Как меня зовут?",
    "Где я работаю и на какой должности?",
    "Какой мой любимый фреймворк и сколько лет я его использую?",
    "Опиши мой текущий проект.",
    "Какую БД я предпочитаю и почему?",
    "Каким инструментом я пишу тесты?",
]


def run_memory_test() -> None:
    print("=" * 60)
    print("СЦЕНАРИЙ 4: ТЕСТ ПАМЯТИ ПОСЛЕ КОМПРЕССИИ")
    print("Оба агента получают одинаковый контекст с личными фактами.")
    print("После компрессии задаём вопросы об этих фактах.")
    print("=" * 60)

    agent_full = Agent(compress=False, name="ПОЛНЫЙ")
    agent_comp = Agent(compress=True,  name="СЖАТЫЙ")

    print("\n--- Фаза 1: наполняем контекст фактами ---\n")
    for msg in MEMORY_SETUP:
        _, sf = agent_full.ask(msg)
        _, sc = agent_comp.ask(msg)
        print(f"  [{sf['turn']:>2}] «{msg[:55]}»   "
              f"full={sf['tokens_full']} tok  "
              f"sent={sc['tokens_sent']} tok")

    print("\n--- Фаза 2: проверяем, что агенты помнят ---\n")
    score_full = 0
    score_comp = 0

    for q in MEMORY_QUESTIONS:
        print(f"\nВопрос: {q}")
        ans_full, _ = agent_full.ask(q)
        ans_comp, _ = agent_comp.ask(q)
        print(f"  [БЕЗ СЖАТИЯ] {ans_full.strip()}")
        print(f"  [СО СЖАТИЕМ] {ans_comp.strip()}")

    print(f"\n{'═'*60}")
    print("Оцени ответы выше вручную: насколько каждый агент")
    print("воспроизвёл конкретные детали (имя, компания, фреймворк и т.д.)")
    print(f"{'═'*60}")
    print(f"  Токены БЕЗ СЖАТИЯ (итого вход): {agent_full.total_input_tokens:,}")
    print(f"  Токены СО СЖАТИЕМ (итого вход): {agent_comp.total_input_tokens:,}")
    savings = agent_full.total_input_tokens - agent_comp.total_input_tokens
    pct = savings / agent_full.total_input_tokens * 100
    print(f"  Экономия:                        {savings:,} tok ({pct:.0f}%)")
    print(f"{'═'*60}")


# ------------------------------------------------------------------ entry point


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"

    dispatch = {
        "nocompress":  run_nocompress,
        "compress":    run_compress,
        "compare":     run_compare,
        "memory_test": run_memory_test,
    }

    if mode not in dispatch:
        print(f"Неизвестный режим: {mode}")
        print(f"Доступны: {', '.join(dispatch)}")
        sys.exit(1)

    dispatch[mode]()


if __name__ == "__main__":
    main()
