"""
Интерактивный чат с агентом, использующим три слоя памяти.

Запуск:
  python main.py          — интерактивный режим
  python main.py demo     — автоматическая демонстрация без ввода
  python main.py clear    — очистить все файлы памяти

Команды в чате:
  /done <текст>   — зафиксировать выполненный шаг в рабочей памяти
  /close          — закрыть текущую задачу
  /profile        — обновить долгосрочный профиль
  /memory         — показать состояние всех слоёв памяти
  /clear-stm      — очистить краткосрочную память (после завершения сессии)
  /exit           — завершить сессию
"""

import sys
import os

from agent import MemoryAgent
from memory import STM_FILE, WM_FILE, LTM_FILE


# ─────────────────────────────────────────── интерактивный чат

def run_chat() -> None:
    agent = MemoryAgent()
    agent.start_session()

    print("Чат запущен. Команды: /done <шаг>  /close  /profile  /memory  /exit\n")

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        # ── Команды
        if user_input == "/exit":
            break

        if user_input == "/clear-stm":
            agent.stm.clear()
            print("  [STM] Краткосрочная память очищена.\n")
            continue

        if user_input == "/memory":
            _print_memory(agent)
            continue

        if user_input == "/profile":
            agent.update_profile()
            continue

        if user_input == "/close":
            agent.close_task()
            print("  [WM] Задача закрыта.\n")
            continue

        if user_input.startswith("/done "):
            agent.task_done(user_input[6:].strip())
            continue

        # ── Обычный диалог
        answer, stats = agent.ask(user_input)
        print(f"Агент: {answer}")
        print(f"  [tok: in={stats['inp_tokens']} out={stats['out_tokens']} "
              f"cost=${stats['cost']:.5f}]\n")

    agent.end_session()


# ─────────────────────────────────────────── авто-демо

def _session_header(n: int, title: str) -> None:
    print("\n" + "█" * 60)
    print(f"  СЕССИЯ {n}: {title}")
    print("█" * 60)


def _print_memory_dump(agent: MemoryAgent, label: str = "СОСТОЯНИЕ ПАМЯТИ") -> None:
    """Полный дамп всех трёх слоёв в консоль."""
    print("\n" + "╔" + "═" * 58 + "╗")
    print(f"║  {label:<56}║")
    print("╠" + "═" * 58 + "╣")

    # LTM
    ltm = agent.ltm
    print("║  [LTM] profile.md" + " " * 40 + "║")
    print(f"║    Имя:        {ltm.name:<42}║")
    print(f"║    Должность:  {ltm.role:<42}║")
    print(f"║    Возраст:    {ltm.age:<42}║")
    stack_short = (ltm.stack[:42]) if ltm.stack else "—"
    print(f"║    Стек:       {stack_short:<42}║")
    src = (ltm.sources[:42]) if ltm.sources else "—"
    print(f"║    Источники:  {src:<42}║")

    print("╠" + "─" * 58 + "╣")

    # WM
    wm = agent.wm
    cur = wm.current_task or "—"
    print(f"║  [WM] workflow.json" + " " * 38 + "║")
    print(f"║    Текущая задача: {cur:<39}║")
    for name, info in wm.tasks.items():
        marker = "▶" if name == wm.current_task else "○"
        status = info["status"]
        row = f"    {marker} {name} [{status}]"
        print(f"║  {row:<56}║")
        for done_item in info["done"]:
            di = f"        ✓ {done_item}"
            print(f"║  {di:<56}║")

    print("╠" + "─" * 58 + "╣")

    # STM
    stm = agent.stm
    print(f"║  [STM] current_dialog.json" + " " * 31 + "║")
    prob = stm.problem or "—"
    print(f"║    Проблема: {prob[:45]:<45}║")
    if stm.solutions:
        print(f"║    Решения:" + " " * 47 + "║")
        for s in stm.solutions:
            sol = f"      • {s['solution']}"
            print(f"║  {sol[:56]:<56}║")
            if s.get("arguments"):
                arg = f"        → {s['arguments']}"
                print(f"║  {arg[:56]:<56}║")
    else:
        print(f"║    Решения: —" + " " * 44 + "║")

    print("╚" + "═" * 58 + "╝\n")


def _dialog(agent: MemoryAgent, turns: list[str]) -> None:
    for msg in turns:
        print(f"\n  Вы: {msg}")
        answer, stats = agent.ask(msg)
        print(f"  Агент: {answer}")
        print(f"  [in={stats['inp_tokens']} out={stats['out_tokens']} cost=${stats['cost']:.5f}]")


def run_demo() -> None:
    """
    Три сессии подряд. В конце каждой — полный дамп памяти.

    Сессия 1: первый запуск — создаём LTM, начинаем задачу, 3 хода.
    Сессия 2: продолжаем задачу — 3 хода, закрываем задачу.
    Сессия 3: новая задача — 2 хода, видим что LTM и история WM сохранились.
    """

    # Чистый старт
    for f in (STM_FILE, WM_FILE, LTM_FILE):
        if os.path.exists(f):
            os.remove(f)

    # ──────────────────────────────────────── СЕССИЯ 1
    _session_header(1, "первый запуск, создаём профиль и задачу")

    a1 = MemoryAgent()

    _print_memory_dump(a1, "ПАМЯТЬ В НАЧАЛЕ СЕССИИ 1 (до заполнения)")

    a1.ltm.name    = "Алексей"
    a1.ltm.role    = "Tech Lead, Python"
    a1.ltm.age     = "34"
    a1.ltm.stack   = "FastAPI, PostgreSQL, Redis, Docker"
    a1.ltm.sources = "официальная документация, RealPython"
    a1.ltm.save()
    a1.wm.new_task("Auth-сервис — JWT + 2FA")

    print("\n  [SYSTEM PROMPT]")
    print("─" * 60)
    print(a1._build_system_prompt())
    print("─" * 60)

    _dialog(a1, [
        "С чего начать проектирование JWT-авторизации для FastAPI?",
    ])
    _print_memory_dump(a1, "ПАМЯТЬ В СЕРЕДИНЕ СЕССИИ 1")

    _dialog(a1, [
        "Какую БД выбрать для токенов и сессий?",
        "Как реализовать 2FA для admin-ролей?",
    ])

    a1.task_done("Выбрали PyJWT + FastAPI security")
    a1.task_done("PostgreSQL для refresh-токенов, Redis для blacklist")
    a1.task_done("2FA через TOTP (pyotp), обязательна для admin")

    _print_memory_dump(a1, "ПАМЯТЬ В КОНЦЕ СЕССИИ 1")
    print("  ⚠️  Сессия завершена. Введите /clear-stm чтобы очистить STM.\n")

    # ──────────────────────────────────────── СЕССИЯ 2
    _session_header(2, "продолжаем задачу, завершаем её")

    a2 = MemoryAgent()
    # эмулируем выбор "продолжить"
    open_tasks = [n for n, i in a2.wm.tasks.items() if i["status"] != "завершена"]
    a2.wm.resume_task(open_tasks[0])

    _print_memory_dump(a2, "ПАМЯТЬ В НАЧАЛЕ СЕССИИ 2")

    print("\n  [SYSTEM PROMPT]")
    print("─" * 60)
    print(a2._build_system_prompt())
    print("─" * 60)

    _dialog(a2, [
        "Напомни, что мы уже решили по auth-сервису.",
        "Как написать pytest-фикстуры для тестирования JWT?",
    ])
    _print_memory_dump(a2, "ПАМЯТЬ В СЕРЕДИНЕ СЕССИИ 2")

    _dialog(a2, [
        "Как деплоить сервис с Docker на Hetzner EU?",
    ])

    a2.task_done("pytest fixtures: TestClient + fakeredis")
    a2.task_done("Docker Compose на Hetzner EU (Frankfurt)")
    a2.close_task()

    _print_memory_dump(a2, "ПАМЯТЬ В КОНЦЕ СЕССИИ 2")
    print("  ⚠️  Сессия завершена. Введите /clear-stm чтобы очистить STM.\n")

    # ──────────────────────────────────────── СЕССИЯ 3
    _session_header(3, "новая задача — LTM и история WM сохранились")

    a3 = MemoryAgent()
    a3.wm.new_task("CI/CD — GitHub Actions + Hetzner")

    _print_memory_dump(a3, "ПАМЯТЬ В НАЧАЛЕ СЕССИИ 3")

    print("\n  [SYSTEM PROMPT]")
    print("─" * 60)
    print(a3._build_system_prompt())
    print("─" * 60)

    _dialog(a3, [
        "Что из прошлой задачи важно учесть при настройке CI/CD?",
    ])
    _print_memory_dump(a3, "ПАМЯТЬ В СЕРЕДИНЕ СЕССИИ 3")

    _dialog(a3, [
        "Как структурировать GitHub Actions для нашего стека?",
    ])

    a3.task_done("Workflow: test → build Docker → push → deploy Hetzner")

    _print_memory_dump(a3, "ПАМЯТЬ В КОНЦЕ СЕССИИ 3")
    print("  ⚠️  Сессия завершена. Введите /clear-stm чтобы очистить STM.\n")


# ─────────────────────────────────────────── очистка

def run_clear() -> None:
    removed = []
    for f in (STM_FILE, WM_FILE, LTM_FILE):
        if os.path.exists(f):
            os.remove(f)
            removed.append(f)
    if removed:
        print(f"Удалено: {', '.join(removed)}")
    else:
        print("Файлы памяти не найдены.")


# ─────────────────────────────────────────── entry point

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"

    dispatch = {
        "chat":  run_chat,
        "demo":  run_demo,
        "clear": run_clear,
    }

    if mode not in dispatch:
        print(f"Режимы: {', '.join(dispatch)}")
        sys.exit(1)

    dispatch[mode]()


def _print_memory(agent: MemoryAgent) -> None:
    _print_memory_dump(agent, "ТЕКУЩЕЕ СОСТОЯНИЕ ПАМЯТИ")


if __name__ == "__main__":
    main()
