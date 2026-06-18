"""
Three-layer memory model:

  SHORT-TERM  — current dialog (in-process list, gone after exit)
  WORKING     — task records stored as JSON entities (workflow.json)
  LONG-TERM   — structured user profile (profile.md)
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
WORKFLOW_FILE = DIR / "workflow.json"
PROFILE_FILE  = DIR / "profile.md"

# State machine: which transitions are allowed
VALID_TRANSITIONS: dict[str, list[str]] = {
    "planning":    ["in-progress"],
    "in-progress": ["review", "planning"],
    "review":      ["done", "in-progress"],
    "done":        [],
}
TASK_STATUSES = tuple(VALID_TRANSITIONS.keys())

PROFILE_FIELDS: dict[str, str] = {
    "name":       "Имя",
    "occupation": "Род деятельности",
    "grade":      "Грейд",
    "stack":      "Стек",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _now_time() -> str:
    return datetime.now().strftime("%H:%M")

def _new_task(name: str) -> dict:
    return {
        "id":         uuid.uuid4().hex[:8],
        "name":       name,
        "status":     "planning",
        "summary":    "",
        "notes":      [],          # list of {"time": "HH:MM", "text": "..."}
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


# ── Short-term (current session only) ─────────────────────────────────────────

class ShortTermMemory:
    def __init__(self) -> None:
        self._messages: list[dict] = []

    def add(self, role: str, content) -> None:
        self._messages.append({"role": role, "content": content})

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()

    def summary(self) -> str:
        n = len(self._messages)
        if n == 0:
            return "(пусто)"
        last = self._messages[-1]
        content = last["content"]
        if isinstance(content, str):
            text = content
        else:
            text = next(
                (b.get("text") or b.get("content") or "" for b in content
                 if b.get("type") in ("text", "tool_result")),
                "[tool_use]",
            )
        snippet = (text or "")[:80].replace("\n", " ")
        return f"{n} сообщ. | последнее [{last['role']}]: {snippet}…"


# ── Working memory (workflow.json) ─────────────────────────────────────────────

class WorkingMemory:
    """
    Stores tasks as JSON objects in workflow.json.

    Schema:
    {
      "current": "<task id>",
      "tasks": [
        {
          "id":         "a1b2c3d4",
          "name":       "Название задачи",
          "status":     "planning | in-progress | review | done",
          "summary":    "Краткое описание состояния",
          "notes":      [{"time": "14:22", "text": "текст заметки"}],
          "created_at": "2026-06-18T10:00:00",
          "updated_at": "2026-06-18T14:22:00"
        }
      ]
    }

    Status transitions (state machine):
      planning → in-progress
      in-progress → review | planning
      review → done | in-progress
      done → (terminal)
    """

    def _load(self) -> dict:
        if WORKFLOW_FILE.exists():
            try:
                return json.loads(WORKFLOW_FILE.read_text("utf-8"))
            except json.JSONDecodeError:
                pass
        return {"current": "", "tasks": []}

    def _save(self, data: dict) -> None:
        WORKFLOW_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), "utf-8"
        )

    def _find(self, data: dict, task_id: str) -> dict | None:
        return next((t for t in data["tasks"] if t["id"] == task_id), None)

    def _find_by_name(self, data: dict, name: str) -> dict | None:
        return next((t for t in data["tasks"] if t["name"] == name), None)

    # Public API ---------------------------------------------------------------

    def get_current_task(self) -> dict | None:
        data = self._load()
        return self._find(data, data["current"])

    def get_tasks(self) -> list[dict]:
        return self._load()["tasks"]

    def get_active_tasks(self) -> list[dict]:
        return [t for t in self.get_tasks() if t["status"] != "done"]

    def add_task(self, name: str) -> str:
        """Create a new task, set it as current. Returns error or ''."""
        data = self._load()
        if self._find_by_name(data, name):
            return f"Задача '{name}' уже существует"
        task = _new_task(name)
        data["tasks"].append(task)
        data["current"] = task["id"]
        self._save(data)
        return ""

    def set_current(self, name: str) -> str:
        data = self._load()
        task = self._find_by_name(data, name)
        if not task:
            return f"Задача '{name}' не найдена"
        data["current"] = task["id"]
        self._save(data)
        return ""

    def set_status(self, new_status: str) -> str:
        if new_status not in VALID_TRANSITIONS:
            return f"Неизвестный статус '{new_status}'. Доступны: {', '.join(TASK_STATUSES)}"
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        old_status = task["status"]
        if new_status not in VALID_TRANSITIONS[old_status]:
            allowed = VALID_TRANSITIONS[old_status]
            if not allowed:
                return f"Задача уже завершена (статус '{old_status}'), переход невозможен"
            return (
                f"Переход {old_status} → {new_status} недопустим. "
                f"Из '{old_status}' можно перейти в: {', '.join(allowed)}"
            )
        task["status"] = new_status
        task["updated_at"] = _now_iso()
        self._save(data)
        return ""

    def set_summary(self, text: str) -> str:
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        task["summary"] = text
        task["updated_at"] = _now_iso()
        self._save(data)
        return ""

    def add_note(self, note: str) -> str:
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи. Создайте: /task new <название>"
        task["notes"].append({"time": _now_time(), "text": note})
        task["updated_at"] = _now_iso()
        self._save(data)
        return ""

    def valid_transitions_for_current(self) -> list[str]:
        task = self.get_current_task()
        if not task:
            return []
        return VALID_TRANSITIONS[task["status"]]

    def to_prompt_text(self) -> str:
        data = self._load()
        tasks = data["tasks"]
        if not tasks:
            return "(нет задач)"
        lines = []
        for t in tasks:
            marker = "→" if t["id"] == data["current"] else " "
            lines.append(f"{marker} [{t['status']}] {t['name']}")
            if t["summary"]:
                lines.append(f"    Саммари: {t['summary']}")
            for n in t["notes"]:
                lines.append(f"    - [{n['time']}] {n['text']}")
        return "\n".join(lines)

    def summary(self) -> str:
        data = self._load()
        tasks = data["tasks"]
        active = [t for t in tasks if t["status"] != "done"]
        cur = self._find(data, data.get("current", ""))
        cur_info = f"[{cur['status']}] {cur['name']}" if cur else "нет"
        return f"current={cur_info} | active={len(active)}/{len(tasks)}"


# ── Long-term memory (profile.md) ─────────────────────────────────────────────

class LongTermMemory:
    """
    profile.md structure:

        # Profile

        Имя: Виктор
        Род деятельности: Backend-разработчик
        Грейд: Middle
        Стек: Python, FastAPI, PostgreSQL
    """

    def load(self) -> dict[str, str]:
        data = {k: "" for k in PROFILE_FIELDS}
        if not PROFILE_FILE.exists():
            return data
        for line in PROFILE_FILE.read_text("utf-8").splitlines():
            for key, label in PROFILE_FIELDS.items():
                prefix = f"{label}: "
                if line.startswith(prefix):
                    data[key] = line[len(prefix):].strip()
        return data

    def _save(self, data: dict[str, str]) -> None:
        lines = ["# Profile", ""]
        for key, label in PROFILE_FIELDS.items():
            lines.append(f"{label}: {data.get(key, '')}")
        PROFILE_FILE.write_text("\n".join(lines) + "\n", "utf-8")

    def set_field(self, key: str, value: str) -> str:
        if key not in PROFILE_FIELDS:
            return f"Неизвестное поле. Доступны: {', '.join(PROFILE_FIELDS)}"
        data = self.load()
        data[key] = value
        self._save(data)
        return ""

    def is_complete(self) -> bool:
        return all(v.strip() for v in self.load().values())

    def to_prompt_text(self) -> str:
        data = self.load()
        return "\n".join(
            f"{label}: {data[key] or '(не указано)'}"
            for key, label in PROFILE_FIELDS.items()
        )

    def summary(self) -> str:
        data = self.load()
        filled = sum(1 for v in data.values() if v.strip())
        name = data.get("name") or "?"
        return f"name={name} | {filled}/{len(PROFILE_FIELDS)} полей заполнено"
