"""
Three-layer memory model — d13.

  SHORT-TERM  — текущий диалог (in-process)
  WORKING     — задачи со стейт-машиной этапов (workflow.json)
  LONG-TERM   — профиль + предпочтения общения (profile.md)

Стейт-машина задачи:
  planning → execution → validation → done
  (откаты: validation → execution, execution → planning)
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).parent
WORKFLOW_FILE = DIR / "workflow.json"
PROFILE_FILE  = DIR / "profile.md"

# ── Stage machine ──────────────────────────────────────────────────────────────

STAGES = ("planning", "execution", "validation", "done")

STAGE_TRANSITIONS: dict[str, list[str]] = {
    "planning":   ["execution"],
    "execution":  ["validation", "planning"],
    "validation": ["done", "execution"],
    "done":       [],
}

# expected_action values
WAITING   = "awaiting_confirm"   # sub-agent finished, waiting /confirm
WORKING   = "in_progress"        # sub-agent is active

# Profile / pref fields
PROFILE_FIELDS: dict[str, str] = {
    "name":       "Имя",
    "occupation": "Род деятельности",
    "grade":      "Грейд",
    "stack":      "Стек",
}
PREF_FIELDS: dict[str, str] = {
    "style":    "Стиль",
    "format":   "Формат",
    "language": "Язык",
    "extras":   "Пожелания",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def _now_time() -> str:
    return datetime.now().strftime("%H:%M")


def _new_task(name: str) -> dict:
    return {
        "id":              uuid.uuid4().hex[:8],
        "name":            name,
        # Stage machine state
        "stage":           "planning",
        "expected_action": WORKING,
        "pending_result":  "",       # last sub-agent output, shown on resume
        # Execution plan
        "plan":            [],       # list of step strings
        "step_index":      0,        # current step index (during execution)
        "step_notes":      [],       # per-step notes, parallel to plan
        # Stage outputs
        "stage_results": {
            "planning":           "",
            "execution":          "",
            "validation":         "",
            "validation_passed":  None,   # bool | None
        },
        "notes":      [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


# ── Short-term ─────────────────────────────────────────────────────────────────

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
    Stores tasks with full stage-machine state in workflow.json.

    Stage flow: planning → execution → validation → done
    expected_action: "in_progress" | "awaiting_confirm"
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

    def _touch(self, task: dict) -> None:
        task["updated_at"] = _now_iso()

    # ── Basic CRUD ─────────────────────────────────────────────────────────────

    def get_current_task(self) -> dict | None:
        data = self._load()
        return self._find(data, data.get("current", ""))

    def get_tasks(self) -> list[dict]:
        return self._load()["tasks"]

    def get_active_tasks(self) -> list[dict]:
        return [t for t in self.get_tasks() if t["stage"] != "done"]

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

    def add_note(self, note: str) -> str:
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        task["notes"].append({"time": _now_time(), "text": note})
        self._touch(task)
        self._save(data)
        return ""

    # ── Planning stage ─────────────────────────────────────────────────────────

    def finish_planning(self, steps: list[str], summary: str) -> str:
        """Planning agent calls this when plan is ready."""
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        if task["stage"] != "planning":
            return f"Задача на этапе '{task['stage']}', не 'planning'"
        task["plan"] = steps
        task["step_notes"] = [""] * len(steps)
        task["stage_results"]["planning"] = summary
        task["expected_action"] = WAITING
        task["pending_result"] = f"**План ({len(steps)} шагов):**\n" + "\n".join(
            f"  {i+1}. {s}" for i, s in enumerate(steps)
        )
        self._touch(task)
        self._save(data)
        return ""

    # ── Execution stage ────────────────────────────────────────────────────────

    def finish_execution(self, step_results: list[str], summary: str) -> str:
        """Execution agent calls this when ALL steps are done."""
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        if task["stage"] != "execution":
            return f"Задача на этапе '{task['stage']}', не 'execution'"
        total = len(task["plan"])
        # Pad/trim results to match plan length
        results = list(step_results) + [""] * total
        task["step_notes"] = results[:total]
        task["stage_results"]["execution"] = summary
        task["expected_action"] = WAITING
        task["pending_result"] = f"**Выполнение завершено ({total} шагов):**\n{summary}"
        self._touch(task)
        self._save(data)
        return ""

    # ── Validation stage ───────────────────────────────────────────────────────

    def finish_validation(self, passed: bool, summary: str) -> str:
        """Validation agent calls this when validation is done."""
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return "Нет текущей задачи"
        if task["stage"] != "validation":
            return f"Задача на этапе '{task['stage']}', не 'validation'"
        task["stage_results"]["validation"] = summary
        task["stage_results"]["validation_passed"] = passed
        icon = "✓" if passed else "✗"
        task["expected_action"] = WAITING
        task["pending_result"] = f"{icon} Валидация: {summary}"
        self._touch(task)
        self._save(data)
        return ""

    # ── Stage transitions (called by /confirm) ─────────────────────────────────

    def confirm_transition(self) -> tuple[str, str]:
        """
        User typed /confirm. Advance the state machine.
        Returns (new_stage_or_action, message).
        """
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return ("", "Нет активной задачи.")
        if task["expected_action"] != WAITING:
            return ("", "Агент ещё не завершил этап — напиши что-нибудь чтобы продолжить диалог, или дождись сообщения ✅.")

        stage = task["stage"]

        if stage == "planning":
            if not task["plan"]:
                return ("", "План не задан. Агент планирования ещё не вызвал finish_planning().")
            task["stage"] = "execution"
            task["step_index"] = 0
            task["expected_action"] = WORKING
            task["pending_result"] = ""
            self._touch(task)
            self._save(data)
            return ("execution", f"Переходим к выполнению. Первый шаг: {task['plan'][0]}")

        if stage == "execution":
            # All steps were done by agent in one shot — go to validation
            task["stage"] = "validation"
            task["expected_action"] = WORKING
            task["pending_result"] = ""
            self._touch(task)
            self._save(data)
            return ("validation", "Выполнение подтверждено. Переходим к валидации.")

        if stage == "validation":
            passed = task["stage_results"].get("validation_passed")
            if passed is True or passed is None:
                task["stage"] = "done"
                task["expected_action"] = "done"
                task["pending_result"] = ""
                self._touch(task)
                self._save(data)
                return ("done", f"Задача '{task['name']}' завершена!")
            else:
                task["stage"] = "execution"
                task["step_index"] = 0
                task["expected_action"] = WORKING
                task["pending_result"] = ""
                self._touch(task)
                self._save(data)
                return ("execution", "Валидация не пройдена. Возвращаемся к выполнению с шага 1.")

        return ("", f"Неизвестный этап: {stage}")

    def rollback(self) -> tuple[str, str]:
        """User typed /back — go to previous stage."""
        data = self._load()
        task = self._find(data, data.get("current", ""))
        if not task:
            return ("", "Нет активной задачи.")
        stage = task["stage"]
        rollback_map = {
            "execution":  "planning",
            "validation": "execution",
        }
        prev = rollback_map.get(stage)
        if not prev:
            return ("", f"Нельзя откатиться с этапа '{stage}'.")
        task["stage"] = prev
        task["expected_action"] = WORKING
        task["pending_result"] = ""
        self._touch(task)
        self._save(data)
        return (prev, f"Откат на этап '{prev}'.")

    # ── Display helpers ────────────────────────────────────────────────────────

    def stage_status_text(self) -> str:
        task = self.get_current_task()
        if not task:
            return "(нет задачи)"
        stage = task["stage"]
        action = task["expected_action"]
        lines = [f"Этап: {stage}  |  Ожидание: {action}"]
        if stage == "execution" and task["plan"]:
            idx = task["step_index"]
            total = len(task["plan"])
            lines.append(f"Шаг: {idx+1}/{total} — {task['plan'][idx]}")
        return "\n".join(lines)

    def to_prompt_text(self) -> str:
        data = self._load()
        tasks = data["tasks"]
        if not tasks:
            return "(нет задач)"
        lines = []
        for t in tasks:
            marker = "→" if t["id"] == data.get("current") else " "
            lines.append(f"{marker} [{t['stage']}] {t['name']}")
        return "\n".join(lines)

    def summary(self) -> str:
        data = self._load()
        tasks = data["tasks"]
        active = [t for t in tasks if t["stage"] != "done"]
        cur = self._find(data, data.get("current", ""))
        if cur:
            stage = cur["stage"]
            if stage == "execution" and cur["plan"]:
                stage += f" ({len(cur['plan'])} шагов)"
            cur_info = f"[{stage}] {cur['name']}"
        else:
            cur_info = "нет"
        return f"current={cur_info} | active={len(active)}/{len(tasks)}"


# ── Long-term memory (profile.md) ─────────────────────────────────────────────

class LongTermMemory:
    """
    profile.md has two sections: # Profile and # Preferences.
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
                    if line.startswith(f"{label}: "):
                        profile[key] = line[len(f"{label}: "):].strip()
            elif section == "prefs":
                for key, label in PREF_FIELDS.items():
                    if line.startswith(f"{label}: "):
                        prefs[key] = line[len(f"{label}: "):].strip()
        return profile, prefs

    def _save_all(self, profile: dict, prefs: dict) -> None:
        lines = ["# Profile", ""]
        for key, label in PROFILE_FIELDS.items():
            lines.append(f"{label}: {profile.get(key, '')}")
        lines.extend(["", "# Preferences", ""])
        for key, label in PREF_FIELDS.items():
            lines.append(f"{label}: {prefs.get(key, '')}")
        PROFILE_FILE.write_text("\n".join(lines) + "\n", "utf-8")

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
        lines = [f"- {label}: {prefs[key]}" for key, label in PREF_FIELDS.items() if prefs[key].strip()]
        return "\n".join(lines) if lines else ""

    def summary(self) -> str:
        profile, prefs = self._parse_file()
        p = sum(1 for v in profile.values() if v.strip())
        r = sum(1 for v in prefs.values() if v.strip())
        name = profile.get("name") or "?"
        return f"name={name} | профиль={p}/{len(PROFILE_FIELDS)} | предпочтения={r}/{len(PREF_FIELDS)}"
