"""
Сравнение трёх стратегий управления контекстом агента.

Сценарий: сбор ТЗ на систему авторизации (12–15 сообщений).
Каждая стратегия прогоняется на одинаковом наборе вопросов,
затем выводится сравнительная таблица.

Запуск:
  python main.py window      — только Sliding Window
  python main.py facts       — только Sticky Facts
  python main.py branching   — только Branching
  python main.py compare     — все три, итоговое сравнение
"""

import sys
from agent import Agent

# ─────────────────────────────────────────── сценарий ТЗ

TZ_DIALOG = [
    # Блок 1: первичные требования (уйдут в sliding window / в факты)
    "Привет! Нам нужна система авторизации для B2B SaaS-платформы.",
    "Ожидаемое количество пользователей: около 50 000 MAU.",
    "Из методов входа нужны: email+пароль, Google OAuth и SSO через SAML.",
    "Все данные должны храниться в ЕС (GDPR). Никаких US-серверов.",
    "Язык бэкенда — Python. Фреймворк — FastAPI.",
    "База данных — PostgreSQL. Redis для сессий.",
    # ← после этого хода sliding window уже теряет ход #1
    "Двухфакторная аутентификация обязательна для admin-ролей.",
    "У нас три роли: viewer, editor, admin. RBAC, не ABAC.",
    "Токены: JWT access 15 минут, refresh 30 дней.",
    "Нужен аудит-лог всех входов и выходов, храним 90 дней.",
    # Блок 2: контрольные вопросы — проверяем память о деталях выше
    "Напомни, какие методы входа мы обсудили?",
    "Какие у нас требования к хранению данных?",
    "Сколько ролей в системе и какие именно?",
    "Каков срок жизни access-токена?",
    "Составь краткое резюме ТЗ на основе всего, что мы обсудили.",
]

BAR = 40


def tok_bar(sent: int, full: int) -> str:
    pct   = min(sent / max(full, 1), 1.0)
    filled = int(BAR * pct)
    return "█" * filled + "░" * (BAR - filled)


def print_stats(stats: dict, strategy: str) -> None:
    s = stats
    saved_pct = s["tokens_saved"] / max(s["tokens_full"], 1) * 100
    branch_tag = f" [{s['branch']}]" if s["branch"] else ""
    print(
        f"    [{strategy}{branch_tag}] "
        f"full={s['tokens_full']:>5} tok  "
        f"sent={s['tokens_sent']:>5} tok  "
        f"saved={s['tokens_saved']:>+5} ({saved_pct:.0f}%)  "
        f"cost=${s['session_cost']:.5f}"
    )
    if strategy == "facts" and s["facts_count"]:
        print(f"    facts в памяти: {s['facts_count']}")


# ─────────────────────────────────────────── scenario runners

def run_strategy(strategy: str, show_answers: bool = True) -> Agent:
    labels = {
        "window":    "СТРАТЕГИЯ 1 — Sliding Window",
        "facts":     "СТРАТЕГИЯ 2 — Sticky Facts",
        "branching": "СТРАТЕГИЯ 3 — Branching",
    }
    print("\n" + "=" * 62)
    print(labels[strategy])
    print("=" * 62)

    agent = Agent(strategy=strategy)

    for i, msg in enumerate(TZ_DIALOG, 1):
        print(f"\n  [{i:>2}] Вы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"       Агент: {answer}")
        print_stats(stats, strategy)

    print(f"\n  {'─'*58}")
    print(f"  ИТОГ: вход={agent.total_input_tokens:,} tok  "
          f"выход={agent.total_output_tokens:,} tok  "
          f"cost=${agent.total_input_tokens*1e-6 + agent.total_output_tokens*5e-6:.5f}")
    if strategy == "facts" and agent.facts:
        print(f"\n  Накопленные facts:")
        for k, v in agent.facts.items():
            print(f"    {k}: {v}")

    return agent


def run_branching_demo() -> Agent:
    """
    Демонстрация ветвления: собираем общее ТЗ, потом разветвляемся —
    в одной ветке делаем акцент на безопасность, в другой — на скорость.
    """
    print("\n" + "=" * 62)
    print("СТРАТЕГИЯ 3 — Branching (полная демонстрация)")
    print("=" * 62)

    agent = Agent(strategy="branching")

    # ── Общий ствол (первые 6 сообщений = база ТЗ)
    print("\n  [ОБЩИЙ СТВОЛ — ветка «main»]")
    for msg in TZ_DIALOG[:6]:
        print(f"\n  Вы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"  Агент: {answer}")
        print_stats(stats, "branching")

    # ── Checkpoint
    print()
    agent.checkpoint()

    # ── Ветка A: акцент на безопасность
    agent.branch("security")
    print("\n  [ВЕТКА «security» — фокус на безопасность]")
    branch_a_questions = [
        "Какие угрозы безопасности критичны для нашей системы авторизации?",
        "Как защититься от brute-force и credential stuffing?",
        "Нужны ли нам rate-limiting и CAPTCHA на форме входа?",
    ]
    for msg in branch_a_questions:
        print(f"\n  Вы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"  Агент: {answer}")
        print_stats(stats, "branching")

    # ── Переключаемся на ветку B
    agent.branch("performance")
    print("\n  [ВЕТКА «performance» — фокус на производительность]")
    branch_b_questions = [
        "Как обеспечить высокую скорость авторизации при 50 000 MAU?",
        "Стоит ли кэшировать JWT или проверять каждый раз?",
        "Какие bottleneck'и возникнут при пиковой нагрузке?",
    ]
    for msg in branch_b_questions:
        print(f"\n  Вы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"  Агент: {answer}")
        print_stats(stats, "branching")

    # ── Возврат к security и контрольный вопрос
    print()
    agent.switch("security")
    print("\n  [Контрольный вопрос в ветке «security»]")
    q = "Напомни: какой у нас стек (язык, БД) и требования к данным?"
    print(f"\n  Вы: {q}")
    answer, stats = agent.ask(q)
    print(f"  Агент: {answer}")
    print_stats(stats, "branching")

    # ── Возврат к performance и контрольный вопрос
    agent.switch("performance")
    print("\n  [Контрольный вопрос в ветке «performance»]")
    print(f"\n  Вы: {q}")
    answer, stats = agent.ask(q)
    print(f"  Агент: {answer}")
    print_stats(stats, "branching")

    print(f"\n  {'─'*58}")
    print(f"  Ветки: {agent.list_branches()}")
    print(f"  ИТОГ: вход={agent.total_input_tokens:,} tok  "
          f"выход={agent.total_output_tokens:,} tok  "
          f"cost=${agent.total_input_tokens*1e-6 + agent.total_output_tokens*5e-6:.5f}")
    return agent


# ─────────────────────────────────────────── compare

def run_compare() -> None:
    print("=" * 62)
    print("СРАВНЕНИЕ ТРЁХ СТРАТЕГИЙ — одинаковый сценарий сбора ТЗ")
    print("=" * 62)

    agents: dict[str, Agent] = {}

    # Запускаем все три (branching — в упрощённом режиме без демо-веток)
    for strategy in ("window", "facts", "branching"):
        a = Agent(strategy=strategy, name=strategy.upper())
        print(f"\n{'─'*62}")
        print(f"  {strategy.upper()}")
        print(f"{'─'*62}")
        for i, msg in enumerate(TZ_DIALOG, 1):
            answer, stats = a.ask(msg)
            # Печатаем только контрольные вопросы (11–15)
            if i >= 11:
                print(f"\n  [{i:>2}] Вы: {msg}")
                print(f"       {strategy.upper()}: {answer}")
                print_stats(stats, strategy)
        agents[strategy] = a

    # ── Финальная таблица
    print(f"\n{'═'*62}")
    print("ФИНАЛЬНОЕ СРАВНЕНИЕ")
    print(f"{'═'*62}")
    print(f"  {'Метрика':<35} {'WINDOW':>8} {'FACTS':>8} {'BRANCH':>8}")
    print(f"  {'─'*59}")

    for label, key in [
        ("Входящих токенов (итого)", "total_input_tokens"),
        ("Исходящих токенов (итого)", "total_output_tokens"),
    ]:
        vals = {s: getattr(agents[s], key) for s in agents}
        print(f"  {label:<35} "
              f"{vals['window']:>8,} "
              f"{vals['facts']:>8,} "
              f"{vals['branching']:>8,}")

    for label, strategy in [("WINDOW", "window"), ("FACTS", "facts"), ("BRANCH", "branching")]:
        a = agents[strategy]
        cost = a.total_input_tokens * 1e-6 + a.total_output_tokens * 5e-6
        print(f"  {'Стоимость ' + label:<35} {'':>8} {'':>8} {'':>8}")

    # Пересчитаем стоимость нормально
    costs = {s: agents[s].total_input_tokens*1e-6 + agents[s].total_output_tokens*5e-6
             for s in agents}
    print(f"  {'Стоимость ($)':<35} "
          f"{costs['window']:>8.5f} "
          f"{costs['facts']:>8.5f} "
          f"{costs['branching']:>8.5f}")

    # Facts — показываем что накоплено
    if agents["facts"].facts:
        print(f"\n  Накопленные facts (стратегия FACTS):")
        for k, v in agents["facts"].facts.items():
            print(f"    {k}: {v}")

    print(f"\n  Характеристики:")
    print(f"  {'':4}WINDOW:    просто, теряет старые детали после {6} сообщений")
    print(f"  {'':4}FACTS:     дороже (доп. вызов на извлечение), но помнит суть")
    print(f"  {'':4}BRANCHING: гибко для альтернатив, не теряет нить внутри ветки")
    print(f"{'═'*62}")


# ─────────────────────────────────────────── entry point

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "compare"

    dispatch = {
        "window":    lambda: run_strategy("window"),
        "facts":     lambda: run_strategy("facts"),
        "branching": run_branching_demo,
        "compare":   run_compare,
    }

    if mode not in dispatch:
        print(f"Неизвестный режим: {mode}")
        print(f"Доступны: {', '.join(dispatch)}")
        sys.exit(1)

    dispatch[mode]()


if __name__ == "__main__":
    main()
