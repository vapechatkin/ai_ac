"""
CLI-агент с явной трёхслойной моделью памяти и tool use.

Слои памяти:
  SHORT-TERM  — текущий диалог (в памяти процесса, сбрасывается при выходе)
  WORKING     — задачи со статусами и заметками (workflow.md)
  LONG-TERM   — структурированный профиль пользователя (profile.md)

Агент получает инструменты для прямого обновления памяти —
когда пользователь просит "обнови статус", модель вызывает tool,
а не просто советует команду.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import anthropic

from memory import ShortTermMemory, WorkingMemory, LongTermMemory, PROFILE_FIELDS, TASK_STATUSES, VALID_TRANSITIONS

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


# ── Tools (инструменты для обновления памяти) ──────────────────────────────────

TOOLS = [
    {
        "name": "set_task_status",
        "description": (
            "Обновить статус текущей задачи. Статусы движутся по графу: "
            "planning → in-progress → review → done (с откатами: review → in-progress, in-progress → planning). "
            "Переходы за пределами графа будут отклонены — в ответе придёт сообщение об ошибке. "
            "Вызывай, когда пользователь явно говорит о начале/завершении работы или смене статуса."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": list(TASK_STATUSES),
                    "description": "Целевой статус задачи",
                }
            },
            "required": ["status"],
        },
    },
    {
        "name": "set_task_summary",
        "description": (
            "Обновить краткое саммари текущей задачи. "
            "Вызывай, когда пользователь подтверждает описание задачи или просит "
            "зафиксировать текущее состояние."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Краткое описание текущего состояния задачи (1-2 предложения)",
                }
            },
            "required": ["summary"],
        },
    },
    {
        "name": "add_note",
        "description": (
            "Добавить заметку к текущей задаче. "
            "Вызывай при важных решениях, фактах, договорённостях, "
            "которые нужно сохранить."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "Текст заметки",
                }
            },
            "required": ["note"],
        },
    },
    {
        "name": "set_profile_field",
        "description": (
            "Обновить поле профиля пользователя. "
            "Вызывай, когда пользователь сообщает о себе новую информацию "
            "(имя, профессия, грейд, стек)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "enum": list(PROFILE_FIELDS.keys()),
                    "description": "Поле: name=Имя, occupation=Род деятельности, grade=Грейд, stack=Стек",
                },
                "value": {
                    "type": "string",
                    "description": "Новое значение",
                },
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "create_task",
        "description": (
            "Создать новую задачу в рабочей памяти и сделать её текущей. "
            "Вызывай, когда пользователь хочет начать работу над новой задачей."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Название новой задачи",
                }
            },
            "required": ["name"],
        },
    },
]


def execute_tool(name: str, inp: dict) -> str:
    """Execute a tool call and return a human-readable result string."""
    if name == "set_task_status":
        err = working.set_status(inp["status"])
        return f"Статус → {inp['status']}" if not err else f"Ошибка: {err}"

    if name == "set_task_summary":
        err = working.set_summary(inp["summary"])
        return "Саммари обновлено" if not err else f"Ошибка: {err}"

    if name == "add_note":
        err = working.add_note(inp["note"])
        return f"Заметка: {inp['note'][:60]}" if not err else f"Ошибка: {err}"

    if name == "set_profile_field":
        err = long_.set_field(inp["field"], inp["value"])
        label = PROFILE_FIELDS.get(inp["field"], inp["field"])
        return f"{label} → {inp['value']}" if not err else f"Ошибка: {err}"

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
║  /task status <статус>    сменить статус текущей задачи          ║
║    статусы: planning | in-progress | review | done               ║
║  /task summary <текст>    обновить саммари текущей задачи        ║
║  /task done               отметить текущую задачу выполненной    ║
║  /note <текст>            добавить заметку к текущей задаче      ║
╠══════════════════════════════════════════════════════════════════╣
║  ПРОФИЛЬ                                                         ║
║  /profile show            показать профиль                       ║
║  /profile name <знач>     изменить имя                           ║
║  /profile occupation <з>  изменить род деятельности              ║
║  /profile grade <знач>    изменить грейд                         ║
║  /profile stack <знач>    изменить стек                          ║
╠══════════════════════════════════════════════════════════════════╣
║  ПРОЧЕЕ                                                          ║
║  /memory                  состояние всех слоёв памяти            ║
║  /clear short             начать диалог заново                   ║
║  /help                    эта справка                            ║
║  /quit                    выход                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

PROFILE_CMD_MAP: dict[str, str] = {
    "name": "name", "occupation": "occupation", "grade": "grade", "stack": "stack",
    "имя": "name", "деятельность": "occupation", "грейд": "grade", "стек": "stack",
}


# ── System prompt ──────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    profile_text  = long_.to_prompt_text()
    workflow_text = working.to_prompt_text()
    cur = working.get_current_task()

    current_block = ""
    if cur:
        notes_lines = "\n".join(
            f"  - [{n['time']}] {n['text']}" for n in cur["notes"]
        ) if cur["notes"] else "  (нет заметок)"
        allowed = VALID_TRANSITIONS[cur["status"]]
        transitions_hint = (
            f"Допустимые переходы из '{cur['status']}': {', '.join(allowed)}"
            if allowed else "Задача завершена, переходы недоступны"
        )
        current_block = f"""
### Текущая задача (детали)
Название    : {cur['name']}
Статус      : {cur['status']}
{transitions_hint}
Саммари     : {cur['summary'] or '(не указано)'}
Обновлено   : {cur['updated_at']}
Заметки     :
{notes_lines}
"""

    return f"""Ты полезный ассистент с явной трёхслойной моделью памяти.

## Профиль пользователя
{profile_text}

## Рабочая память — все задачи
{workflow_text}
{current_block}
## Инструменты памяти (ВАЖНО)
У тебя есть инструменты для прямого обновления памяти.
Используй их сразу, без лишних вопросов, когда:
- пользователь явно просит обновить статус, саммари, заметку или профиль;
- пользователь говорит "выполни", "запиши", "обнови", "зафиксируй" — применительно к памяти;
- контекст диалога однозначно указывает на нужное значение.

Статусы двигаются строго по графу. Если вызов set_task_status вернул ошибку перехода —
сообщи пользователю какие переходы допустимы из текущего статуса.

## Инструкции
- Отвечай с учётом профиля и контекста задачи.
- Когда пользователь принимает важное решение — предложи зафиксировать через add_note.
- Будь лаконичен.
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
                # list of blocks — tool_use / tool_result / text
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
            # wrap long lines
            max_w = 56
            while text:
                print(f"  {i:>2}. {role}: {text[:max_w]}")
                text = text[max_w:]
                i = ""  # blank index for continuation lines
                role = "     "

    # WORKING
    _section("WORKING  (рабочая память — задачи)")
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
                print(f"       {note}")

    # LONG-TERM
    _section("LONG-TERM  (профиль пользователя)")
    data = long_.load()
    for key, label in PROFILE_FIELDS.items():
        val = data.get(key) or "(не указано)"
        print(f"  {label}: {val}")

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
        note = cmd[6:].strip()
        err = working.add_note(note)
        print(f"Ошибка: {err}" if err else f"[WORKING] Заметка добавлена: {note}")
        return True

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
                    summary_part = f"  — {t['summary']}" if t["summary"] else ""
                    print(f"  {marker} [{t['status']}] {t['name']}{summary_part}")
                print()
        elif rest.startswith("new "):
            name = rest[4:].strip()
            err = working.add_task(name)
            print(f"Ошибка: {err}" if err else f"[WORKING] Создана задача: {name}")
        elif rest.startswith("use "):
            name = rest[4:].strip()
            err = working.set_current(name)
            print(f"Ошибка: {err}" if err else f"[WORKING] Текущая задача: {name}")
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
                sub, value = parts
                field_key = PROFILE_CMD_MAP.get(sub.lower())
                if field_key:
                    err = long_.set_field(field_key, value.strip())
                    print(f"Ошибка: {err}" if err else
                          f"[LONG-TERM] {PROFILE_FIELDS[field_key]}: {value.strip()}")
                else:
                    print(f"Неизвестное поле: {sub}  (доступны: name, occupation, grade, stack)")
            else:
                print("Использование: /profile show | /profile <поле> <значение>")
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
            # Collect content blocks for the assistant turn
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

            # Store assistant turn (with tool_use blocks) and tool results
            short.add("assistant", assistant_blocks)
            short.add("user", tool_results)
            # Loop: send tool results back to get final reply

        else:
            # Final text response
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
    # 1. Profile check
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

    # 2. Task check
    active = working.get_active_tasks()
    if active:
        print(f"\n📋 Незавершённые задачи ({len(active)}):")
        for i, t in enumerate(active, 1):
            summary_part = f"  — {t['summary']}" if t["summary"] else ""
            print(f"  {i}. [{t['status']}] {t['name']}{summary_part}")
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
