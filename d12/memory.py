"""
Three-layer memory model:

  SHORT-TERM  — current dialog (in-process list, gone after exit)
  WORKING     — task records stored as JSON entities (workflow.json)
  LONG-TERM   — user profile + conversation preferences (profile.md)
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

# Identity fields
PROFILE_FIELDS: dict[str, str] = {
    "name":       "Имя",
    "occupation": "Род деятельности",
    "grade":      "Грейд",
    "stack":      "Стек",
}

# Conversation preference fields (optional — don't block startup)
PREF_FIELDS: dict[str, str] = {
    "style":    "Стиль",      # неформальный / формальный / технический
    "format":   "Формат",     # кратко / подробно / с примерами кода / markdown
    "language": "Язык",       # русский / английский / любой
    "extras":   "Пожелания",  # free-form anything
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
        "notes":      [],
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

    def get_current_task(self) -> dict | None:
        data = self._load()
        return self._find(data, data["current"])

    def get_tasks(self) -> list[dict]:
        return self._load()["tasks"]

    def get_active_tasks(self) -> list[dict]:
        return [t for t in self.get_tasks() if t["status"] != "done"]

    def add_task(self, name: str) -> str:
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
    profile.md stores two sections:

        # Profile

        Имя: Витя
        Род деятельности: ИИ инженер
        Грейд: Джун
        Стек: python, clean arch, ai

        # Preferences

        Стиль: неформальный
        Формат: кратко, с примерами кода
        Язык: русский
        Пожелания: без воды
    """

    def _parse_file(self) -> tuple[dict[str, str], dict[str, str]]:
        profile = {k: "" for k in PROFILE_FIELDS}
        prefs   = {k: "" for k in PREF_FIELDS}
        if not PROFILE_FILE.exists():
            return profile, prefs
        section = None
        for line in PROFILE_FILE.read_text("utf-8").splitlines():
            stripped = line.strip()
            if stripped == "# Profile":
                section = "profile"
            elif stripped == "# Preferences":
                section = "prefs"
            elif section == "profile":
                for key, label in PROFILE_FIELDS.items():
                    prefix = f"{label}: "
                    if line.startswith(prefix):
                        profile[key] = line[len(prefix):].strip()
            elif section == "prefs":
                for key, label in PREF_FIELDS.items():
                    prefix = f"{label}: "
                    if line.startswith(prefix):
                        prefs[key] = line[len(prefix):].strip()
        return profile, prefs

    def _save_all(self, profile: dict[str, str], prefs: dict[str, str]) -> None:
        lines = ["# Profile", ""]
        for key, label in PROFILE_FIELDS.items():
            lines.append(f"{label}: {profile.get(key, '')}")
        lines.extend(["", "# Preferences", ""])
        for key, label in PREF_FIELDS.items():
            lines.append(f"{label}: {prefs.get(key, '')}")
        PROFILE_FILE.write_text("\n".join(lines) + "\n", "utf-8")

    # Profile ------------------------------------------------------------------

    def load(self) -> dict[str, str]:
        profile, _ = self._parse_file()
        return profile

    def set_field(self, key: str, value: str) -> str:
        if key not in PROFILE_FIELDS:
            return f"Неизвестное поле профиля. Доступны: {', '.join(PROFILE_FIELDS)}"
        profile, prefs = self._parse_file()
        profile[key] = value
        self._save_all(profile, prefs)
        return ""

    def is_complete(self) -> bool:
        return all(v.strip() for v in self.load().values())

    def to_prompt_text(self) -> str:
        data = self.load()
        return "\n".join(
            f"{label}: {data[key] or '(не указано)'}"
            for key, label in PROFILE_FIELDS.items()
        )

    # Preferences --------------------------------------------------------------

    def load_prefs(self) -> dict[str, str]:
        _, prefs = self._parse_file()
        return prefs

    def set_pref(self, key: str, value: str) -> str:
        if key not in PREF_FIELDS:
            return f"Неизвестное поле предпочтений. Доступны: {', '.join(PREF_FIELDS)}"
        profile, prefs = self._parse_file()
        prefs[key] = value
        self._save_all(profile, prefs)
        return ""

    def has_prefs(self) -> bool:
        return any(v.strip() for v in self.load_prefs().values())

    def prefs_to_prompt_text(self) -> str:
        prefs = self.load_prefs()
        lines = []
        for key, label in PREF_FIELDS.items():
            val = prefs[key].strip()
            if val:
                lines.append(f"- {label}: {val}")
        return "\n".join(lines) if lines else "(не заданы)"

    # Summary ------------------------------------------------------------------

    def summary(self) -> str:
        profile, prefs = self._parse_file()
        p_filled = sum(1 for v in profile.values() if v.strip())
        r_filled = sum(1 for v in prefs.values() if v.strip())
        name = profile.get("name") or "?"
        return (
            f"name={name} | профиль={p_filled}/{len(PROFILE_FIELDS)} | "
            f"предпочтения={r_filled}/{len(PREF_FIELDS)}"
        )
