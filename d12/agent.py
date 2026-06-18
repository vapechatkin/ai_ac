"""
CLI-агент с явной трёхслойной моделью памяти и tool use.

Слои памяти:
  SHORT-TERM  — текущий диалог
  WORKING     — задачи со статусами (workflow.json)
  LONG-TERM   — профиль пользователя + предпочтения общения (profile.md)
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic

from memory import (
    ShortTermMemory, WorkingMemory, LongTermMemory,
    PROFILE_FIELDS, PREF_FIELDS, TASK_STATUSES, VALID_TRANSITIONS,
)

# ── Init ───────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")
API_KEY = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    sys.exit("ERROR: CLAUDE_API_KEY not found in .env")

client  = anthropic.Anthropic(api_key=API_KEY)
MODEL   = "claude-opus-4-8"

short   = ShortTermMemory()
working = WorkingMemory()
long_   = LongTermMemory()


# ── Tools ──────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "set_task_status",
        "description": (
            "Обновить статус текущей задачи. Граф переходов: "
            "planning → in-progress → review → done "
            "(откаты: review → in-progress, in-progress → planning). "
            "Переходы вне графа возвращают ошибку."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": list(TASK_STATUSES),
                    "description": "Целевой статус",
                }
            },
            "required": ["status"],
        },
    },
    {
        "name": "set_task_summary",
        "description": (
            "Обновить краткое саммари текущей задачи. "
            "Вызывай, когда пользователь фиксирует состояние задачи."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "1-2 предложения о состоянии задачи"}
            },
            "required": ["summary"],
        },
    },
    {
        "name": "add_note",
        "description": "Добавить заметку к текущей задаче (решения, факты, договорённости).",
        "input_schema": {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": ["note"],
        },
    },
    {
        "name": "set_profile_field",
        "description": (
            "Обновить поле профиля (кто пользователь). "
            "Поля: name=Имя, occupation=Род деятельности, grade=Грейд, stack=Стек."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": list(PROFILE_FIELDS.keys()),
                },
                "value": {"type": "string"},
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "set_pref_field",
        "description": (
            "Обновить предпочтение общения пользователя. "
            "Вызывай СРАЗУ и БЕЗ ВОПРОСОВ, когда пользователь говорит как хочет общаться: "
            "'отвечай покороче', 'пиши по-русски', 'без лишней вежливости', "
            "'давай формально', 'хочу примеры кода' и т.д. "
            "Поля: style=Стиль, format=Формат, language=Язык, extras=Пожелания."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": list(PREF_FIELDS.keys()),
                    "description": "style / format / language / extras",
                },
                "value": {"type": "string", "description": "Новое значение предпочтения"},
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "create_task",
        "description": "Создать новую задачу и сделать её текущей.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
]


def execute_tool(name: str, inp: dict) -> str:
    if name == "set_task_status":
        err = working.set_status(inp["status"])
        return f"Статус → {inp['status']}" if not err else f"Ошибка: {err}"

    if name == "set_task_summary":
        err = working.set_summary(inp["summary"])
        return "Саммари обновлено" if not err else f"Ошибка: {err}"

    if name == "add_note":
        err = working.add_note(inp["note"])
        return f"Заметка сохранена" if not err else f"Ошибка: {err}"

    if name == "set_profile_field":
        err = long_.set_field(inp["field"], inp["value"])
        label = PROFILE_FIELDS.get(inp["field"], inp["field"])
        return f"{label} → {inp['value']}" if not err else f"Ошибка: {err}"

    if name == "set_pref_field":
        err = long_.set_pref(inp["field"], inp["value"])
        label = PREF_FIELDS.get(inp["field"], inp["field"])
        return f"[предпочтение] {label} → {inp['value']}" if not err else f"Ошибка: {err}"

    if name == "create_task":
        err = working.add_task(inp["name"])
        return f"Задача создана: {inp['name']}" if not err else f"Ошибка: {err}"

    return f"Неизвестный инструмент: {name}"


# ── Help text ──────────────────────────────────────────────────────────────────

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════════╗
║                          КОМАНДЫ                                 ║
╠══════════════════════════════════════════════════════════════════╣
║  ЗАДАЧИ                                                          ║
║  /task new <название>     создать задачу и сделать текущей       ║
║  /task list               список всех задач                      ║
║  /task use <название>     переключиться на задачу                ║
║  /task status <статус>    сменить статус (по графу переходов)    ║
║    planning → in-progress → review → done                        ║
║  /task summary <текст>    обновить саммари текущей задачи        ║
║  /task done               отметить выполненной                   ║
║  /note <текст>            добавить заметку к текущей задаче      ║
╠══════════════════════════════════════════════════════════════════╣
║  ПРОФИЛЬ                                                         ║
║  /profile show            показать профиль                       ║
║  /profile name <знач>     изменить имя                           ║
║  /profile occupation <з>  изменить род деятельности              ║
║  /profile grade <знач>    изменить грейд                         ║
║  /profile stack <знач>    изменить стек                          ║
╠══════════════════════════════════════════════════════════════════╣
║  ПРЕДПОЧТЕНИЯ ОБЩЕНИЯ                                            ║
║  /pref show               показать предпочтения                  ║
║  /pref style <знач>       стиль (неформальный / формальный / …)  ║
║  /pref format <знач>      формат (кратко / подробно / …)         ║
║  /pref language <знач>    язык (русский / английский / …)        ║
║  /pref extras <знач>      любые пожелания в свободной форме      ║
╠══════════════════════════════════════════════════════════════════╣
║  ПРОЧЕЕ                                                          ║
║  /memory                  показать всё состояние памяти          ║
║  /clear short             сбросить диалог                        ║
║  /help                    эта справка                            ║
║  /quit                    выход                                  ║
╚══════════════════════════════════════════════════════════════════╝

Агент сам обновляет предпочтения, когда слышит "отвечай покороче",
"давай без примеров", "пиши по-английски" и т.д.
"""

PROFILE_CMD_MAP: dict[str, str] = {
    "name": "name", "occupation": "occupation", "grade": "grade", "stack": "stack",
    "имя": "name", "деятельность": "occupation", "грейд": "grade", "стек": "stack",
}

PREF_CMD_MAP: dict[str, str] = {
    "style": "style", "format": "format", "language": "language", "extras": "extras",
    "стиль": "style", "формат": "format", "язык": "language", "пожелания": "extras",
}


# ── System prompt ──────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    prefs_text    = long_.prefs_to_prompt_text()
    profile_text  = long_.to_prompt_text()
    workflow_text = working.to_prompt_text()
    cur = working.get_current_task()

    # Preferences block — at the top so it has highest influence
    prefs_block = ""
    if long_.has_prefs():
        prefs_block = f"""
## Правила общения (строго соблюдай в каждом ответе)
{prefs_text}

"""

    current_block = ""
    if cur:
        notes_lines = "\n".join(
            f"  - [{n['time']}] {n['text']}" for n in cur["notes"]
        ) if cur["notes"] else "  (нет заметок)"
        allowed = VALID_TRANSITIONS[cur["status"]]
        transitions_hint = (
            f"Допустимые переходы: {', '.join(allowed)}"
            if allowed else "Задача завершена, переходы недоступны"
        )
        current_block = f"""
### Текущая задача
Название  : {cur['name']}
Статус    : {cur['status']}  ({transitions_hint})
Саммари   : {cur['summary'] or '(не указано)'}
Обновлено : {cur['updated_at']}
Заметки   :
{notes_lines}
"""

    return f"""Ты полезный ассистент с явной трёхслойной моделью памяти.
{prefs_block}
## Профиль пользователя
{profile_text}

## Рабочая память — задачи
{workflow_text}
{current_block}
## Инструменты памяти
Используй инструменты сразу, без уточнений, когда:
- пользователь просит обновить статус / саммари / заметку / профиль;
- пользователь говорит как хочет общаться — обновляй set_pref_field немедленно;
- контекст однозначно указывает нужное значение.

Если set_task_status вернул ошибку перехода — сообщи допустимые варианты.
"""


def build_messages_for_api() -> list[dict]:
    return short.get_messages()


# ── Memory display ─────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def show_memory() -> None:
    print("\n" + "═" * 60)
    print("  СОСТОЯНИЕ ПАМЯТИ")
    print("═" * 60)

    # SHORT-TERM
    _section("SHORT-TERM  (текущий диалог)")
    msgs = short.get_messages()
    if not msgs:
        print("  (пусто)")
    else:
        for i, m in enumerate(msgs, 1):
            role = "Вы   " if m["role"] == "user" else "Агент"
            content = m["content"]
            if isinstance(content, str):
                text = content
            else:
                parts = []
                for b in content:
                    t = b.get("type", "")
                    if t == "text":
                        parts.append(b["text"])
                    elif t == "tool_use":
                        parts.append(f"[tool:{b['name']} {b['input']}]")
                    elif t == "tool_result":
                        parts.append(f"[result:{b['content']}]")
                text = " | ".join(parts)
            max_w = 56
            idx: int | str = i
            while text:
                print(f"  {idx:>2}. {role}: {text[:max_w]}")
                text = text[max_w:]
                idx = ""
                role = "     "

    # WORKING
    _section("WORKING  (задачи)")
    tasks = working.get_tasks()
    if not tasks:
        print("  (нет задач)")
    else:
        cur = working.get_current_task()
        cur_name = cur["name"] if cur else ""
        for t in tasks:
            marker = "→" if t["name"] == cur_name else " "
            print(f"  {marker} [{t['status']}] {t['name']}")
            if t["summary"]:
                print(f"       Саммари: {t['summary']}")
            for note in t["notes"]:
                print(f"       - [{note['time']}] {note['text']}")

    # LONG-TERM: profile
    _section("LONG-TERM  (профиль пользователя)")
    profile = long_.load()
    for key, label in PROFILE_FIELDS.items():
        val = profile.get(key) or "(не указано)"
        print(f"  {label}: {val}")

    # LONG-TERM: preferences
    _section("LONG-TERM  (предпочтения общения)")
    prefs = long_.load_prefs()
    any_pref = False
    for key, label in PREF_FIELDS.items():
        val = prefs.get(key, "").strip()
        if val:
            print(f"  {label}: {val}")
            any_pref = True
    if not any_pref:
        print("  (не заданы — агент адаптируется по ходу разговора)")

    print("\n" + "═" * 60 + "\n")


# ── Command handler ────────────────────────────────────────────────────────────

def handle_command(raw: str) -> bool:
    cmd = raw.strip()

    if cmd == "/help":
        print(HELP_TEXT)
        return True

    if cmd == "/memory":
        show_memory()
        return True

    if cmd in ("/quit", "/exit"):
        print("До свидания!")
        sys.exit(0)

    if cmd == "/clear short":
        short.clear()
        print("[SHORT-TERM] Диалог сброшен.")
        return True

    if cmd.startswith("/note "):
        err = working.add_note(cmd[6:].strip())
        print(f"Ошибка: {err}" if err else "[WORKING] Заметка добавлена.")
        return True

    # /task …
    if cmd.startswith("/task"):
        rest = cmd[5:].strip()
        if rest == "list":
            tasks = working.get_tasks()
            if not tasks:
                print("Задач нет. Создайте: /task new <название>")
            else:
                cur = working.get_current_task()
                cur_name = cur["name"] if cur else ""
                print()
                for t in tasks:
                    marker = "→" if t["name"] == cur_name else " "
                    s = f"  — {t['summary']}" if t["summary"] else ""
                    print(f"  {marker} [{t['status']}] {t['name']}{s}")
                print()
        elif rest.startswith("new "):
            err = working.add_task(rest[4:].strip())
            print(f"Ошибка: {err}" if err else f"[WORKING] Создана задача: {rest[4:].strip()}")
        elif rest.startswith("use "):
            err = working.set_current(rest[4:].strip())
            print(f"Ошибка: {err}" if err else f"[WORKING] Текущая задача: {rest[4:].strip()}")
        elif rest == "done":
            err = working.set_status("done")
            print(f"Ошибка: {err}" if err else "[WORKING] Задача выполнена.")
        elif rest.startswith("status "):
            err = working.set_status(rest[7:].strip())
            print(f"Ошибка: {err}" if err else f"[WORKING] Статус: {rest[7:].strip()}")
        elif rest.startswith("summary "):
            err = working.set_summary(rest[8:].strip())
            print(f"Ошибка: {err}" if err else "[WORKING] Саммари обновлено.")
        else:
            print("Использование: /task new|list|use|status|summary|done  (или /help)")
        return True

    # /profile …
    if cmd.startswith("/profile"):
        rest = cmd[8:].strip()
        if not rest or rest == "show":
            data = long_.load()
            print()
            for key, label in PROFILE_FIELDS.items():
                print(f"  {label}: {data.get(key) or '(не указано)'}")
            print()
        else:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                field_key = PROFILE_CMD_MAP.get(parts[0].lower())
                if field_key:
                    err = long_.set_field(field_key, parts[1].strip())
                    print(f"Ошибка: {err}" if err else
                          f"[ПРОФИЛЬ] {PROFILE_FIELDS[field_key]}: {parts[1].strip()}")
                else:
                    print(f"Неизвестное поле: {parts[0]}  (доступны: name, occupation, grade, stack)")
            else:
                print("Использование: /profile show | /profile <поле> <значение>")
        return True

    # /pref …
    if cmd.startswith("/pref"):
        rest = cmd[5:].strip()
        if not rest or rest == "show":
            prefs = long_.load_prefs()
            print()
            for key, label in PREF_FIELDS.items():
                val = prefs.get(key) or "(не задано)"
                print(f"  {label}: {val}")
            print()
        else:
            parts = rest.split(" ", 1)
            if len(parts) == 2:
                field_key = PREF_CMD_MAP.get(parts[0].lower())
                if field_key:
                    err = long_.set_pref(field_key, parts[1].strip())
                    print(f"Ошибка: {err}" if err else
                          f"[ПРЕДПОЧТЕНИЯ] {PREF_FIELDS[field_key]}: {parts[1].strip()}")
                else:
                    print(f"Неизвестное поле: {parts[0]}  (доступны: style, format, language, extras)")
            else:
                print("Использование: /pref show | /pref <поле> <значение>")
        return True

    if cmd.startswith("/"):
        print(f"Неизвестная команда: {cmd}  (введите /help для справки)")
        return True

    return False


# ── LLM call with tool use loop ────────────────────────────────────────────────

def chat(user_input: str) -> str:
    short.add("user", user_input)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=build_system_prompt(),
            messages=build_messages_for_api(),
            tools=TOOLS,
        )

        if response.stop_reason == "tool_use":
            assistant_blocks = []
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    assistant_blocks.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    assistant_blocks.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    result = execute_tool(block.name, block.input)
                    print(f"  [ПАМЯТЬ] {result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            short.add("assistant", assistant_blocks)
            short.add("user", tool_results)

        else:
            reply = "\n".join(b.text for b in response.content if b.type == "text")
            short.add("assistant", reply)
            return reply


# ── Startup flow ───────────────────────────────────────────────────────────────

def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def startup_flow() -> None:
    # 1. Profile (required)
    if not long_.is_complete():
        data = long_.load()
        missing = [label for key, label in PROFILE_FIELDS.items() if not data[key].strip()]
        print(f"\n⚠  Профиль не заполнен (отсутствует: {', '.join(missing)}).")
        if _ask("Заполнить сейчас? (y/n): ").lower() == "y":
            for key, label in PROFILE_FIELDS.items():
                cur = data.get(key, "")
                prompt = f"  {label}" + (f" [{cur}]" if cur else "") + ": "
                val = _ask(prompt)
                if val:
                    long_.set_field(key, val)
            print("[ПРОФИЛЬ] Сохранён.\n")

    # 2. Preferences (optional, only if not set yet)
    if not long_.has_prefs():
        print("\n💬 Предпочтения общения не заданы.")
        print("   Агент подстроится автоматически, но можно задать сейчас.")
        if _ask("Настроить? (y/n): ").lower() == "y":
            print("  (Enter — пропустить поле)")
            for key, label in PREF_FIELDS.items():
                examples = {
                    "style":    "напр: неформальный, технический, строгий",
                    "format":   "напр: кратко, подробно, с примерами кода",
                    "language": "напр: русский, английский",
                    "extras":   "напр: без эмодзи, не повторяй вопрос",
                }
                val = _ask(f"  {label} ({examples.get(key, '')}): ")
                if val:
                    long_.set_pref(key, val)
            print("[ПРЕДПОЧТЕНИЯ] Сохранены.\n")
        else:
            print("  Ок — просто скажи в разговоре, например: 'отвечай покороче'.\n")

    # 3. Active tasks
    active = working.get_active_tasks()
    if active:
        print(f"\n📋 Незавершённые задачи ({len(active)}):")
        for i, t in enumerate(active, 1):
            s = f"  — {t['summary']}" if t["summary"] else ""
            print(f"  {i}. [{t['status']}] {t['name']}{s}")
        print("  n. Создать новую задачу\n  (Enter — пропустить)")
        ans = _ask("Выберите (номер / n / Enter): ")
        if ans.isdigit() and 1 <= int(ans) <= len(active):
            chosen = active[int(ans) - 1]
            working.set_current(chosen["name"])
            print(f"[РАБОЧАЯ ПАМЯТЬ] Продолжаем: {chosen['name']}\n")
        elif ans.lower() == "n":
            name = _ask("Название новой задачи: ")
            if name:
                err = working.add_task(name)
                print(f"Ошибка: {err}" if err else f"[РАБОЧАЯ ПАМЯТЬ] Создана задача: {name}\n")
    else:
        print("\n📋 Незавершённых задач нет.")
        if _ask("Создать новую задачу? (y/n): ").lower() == "y":
            name = _ask("Название задачи: ")
            if name:
                err = working.add_task(name)
                print(f"Ошибка: {err}" if err else f"[РАБОЧАЯ ПАМЯТЬ] Создана задача: {name}\n")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 66)
    print("  CLI-агент с трёхслойной памятью  |  /help — справка  |  /quit — выход")
    print("=" * 66)

    startup_flow()
    show_memory()

    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо свидания!")
            break

        if not user_input:
            continue

        if handle_command(user_input):
            continue

        print("Агент: ", end="", flush=True)
        reply = chat(user_input)
        print(reply)
        print()


if __name__ == "__main__":
    main()
