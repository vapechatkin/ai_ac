# memory.py
#
# Три слоя памяти с явными жизненными циклами:
#
#   ShortTermMemory  — stm.json
#     Жизненный цикл: пока жив терминал (процесс).
#     Содержит: основная проблема + предложенные решения с аргументацией.
#     Автоматически обновляется после каждого хода (LLM-экстракция).
#     Пишется в JSON при каждом обновлении. Очищается при завершении процесса
#     (файл удаляется при старте следующей сессии).
#
#   WorkingMemory    — working_memory.json
#     Жизненный цикл: накапливается между сессиями.
#     Структура: MAP {задача → {что сделано, статус, дата}}.
#     При старте спрашивает: продолжить старую задачу или новую?
#
#   LongTermMemory   — long_term_memory.md
#     Жизненный цикл: постоянная.
#     Содержит: профиль (имя/должность/возраст), стек, источники.
#     Перезаписывается только при отсутствии или по запросу пользователя.

import json
import os
import re
from datetime import datetime

STM_FILE = "current_dialog.json"
WM_FILE  = "workflow.json"
LTM_FILE = "profile.md"


# ─────────────────────────────────────────── ShortTermMemory

class ShortTermMemory:
    """
    Саммари текущей сессии: проблема + решения с аргументами.
    Пишется в stm.json при каждом обновлении.
    Удаляется при старте новой сессии (start_session очищает файл).
    """

    def __init__(self, path: str = STM_FILE):
        self._path     = path
        self.problem:   str        = ""
        self.solutions: list[dict] = []

    def clear(self) -> None:
        """Вызывается при старте сессии — предыдущая STM не нужна."""
        self.problem   = ""
        self.solutions = []
        if os.path.exists(self._path):
            os.remove(self._path)

    def update(self, problem: str, solutions: list[dict]) -> None:
        self.problem   = problem
        self.solutions = solutions
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"problem": self.problem, "solutions": self.solutions},
                      f, ensure_ascii=False, indent=2)

    def is_empty(self) -> bool:
        return not self.problem

    def to_prompt_block(self) -> str:
        if self.is_empty():
            return ""
        lines = ["[КРАТКОСРОЧНАЯ ПАМЯТЬ — текущий диалог]",
                 f"Проблема: {self.problem}"]
        if self.solutions:
            lines.append("Предложенные решения:")
            for s in self.solutions:
                lines.append(f"  • {s['solution']}")
                if s.get("arguments"):
                    lines.append(f"    Аргументы: {s['arguments']}")
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "problem":   self.problem[:60] + "..." if len(self.problem) > 60 else self.problem,
            "solutions": len(self.solutions),
        }


# ─────────────────────────────────────────── WorkingMemory

class WorkingMemory:
    """
    MAP задача → {что сделано, статус, даты}.
    Накапливается между сессиями в working_memory.json.
    """

    def __init__(self, path: str = WM_FILE):
        self._path        = path
        self.tasks:        dict[str, dict] = {}
        self.current_task: str             = ""
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            data = json.loads(open(self._path, encoding="utf-8").read())
            self.tasks        = data.get("tasks", {})
            self.current_task = data.get("current_task", "")
        except (json.JSONDecodeError, KeyError):
            pass

    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"tasks": self.tasks, "current_task": self.current_task},
                      f, ensure_ascii=False, indent=2)

    def has_tasks(self) -> bool:
        return bool(self.tasks)

    def task_names(self) -> list[str]:
        return list(self.tasks)

    def new_task(self, name: str) -> None:
        self.tasks[name] = {
            "done":       [],
            "status":     "в процессе",
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.current_task = name
        self.save()

    def resume_task(self, name: str) -> None:
        if name not in self.tasks:
            raise KeyError(f"Задача «{name}» не найдена")
        self.current_task = name
        self.tasks[name]["status"]     = "в процессе"
        self.tasks[name]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.save()

    def add_done(self, item: str) -> None:
        if not self.current_task:
            return
        self.tasks[self.current_task]["done"].append(item)
        self.tasks[self.current_task]["updated_at"] = \
            datetime.now().isoformat(timespec="seconds")
        self.save()

    def close_task(self) -> None:
        if not self.current_task:
            return
        self.tasks[self.current_task]["status"]     = "завершена"
        self.tasks[self.current_task]["updated_at"] = \
            datetime.now().isoformat(timespec="seconds")
        self.current_task = ""
        self.save()

    def to_prompt_block(self) -> str:
        if not self.tasks:
            return ""
        lines = ["[РАБОЧАЯ ПАМЯТЬ — задачи]"]
        for name, info in self.tasks.items():
            marker = "▶" if name == self.current_task else "○"
            lines.append(f"  {marker} {name} [{info['status']}]")
            for done_item in info["done"][-5:]:  # последние 5 пунктов
                lines.append(f"      ✓ {done_item}")
        return "\n".join(lines)

    def current_task_block(self) -> str:
        if not self.current_task:
            return ""
        info  = self.tasks[self.current_task]
        lines = [f"[ТЕКУЩАЯ ЗАДАЧА: {self.current_task}]"]
        lines.append(f"Статус: {info['status']}")
        if info["done"]:
            lines.append("Что сделано:")
            for item in info["done"]:
                lines.append(f"  ✓ {item}")
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "tasks":        list(self.tasks),
            "current_task": self.current_task or "—",
        }


# ─────────────────────────────────────────── LongTermMemory

class LongTermMemory:
    """
    Профиль пользователя в Markdown.
    Перезаписывается только при отсутствии или по запросу пользователя.
    """

    REQUIRED = ["name", "role", "age", "stack"]

    def __init__(self, path: str = LTM_FILE):
        self._path   = path
        self.name:    str = ""
        self.role:    str = ""
        self.age:     str = ""
        self.stack:   str = ""
        self.sources: str = ""
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        text = open(self._path, encoding="utf-8").read()

        def field(label: str) -> str:
            m = re.search(rf"\*\*{label}:\*\*\s*(.+)", text)
            return m.group(1).strip() if m else ""

        def section(header: str) -> str:
            m = re.search(rf"## {header}\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
            return m.group(1).strip() if m else ""

        self.name    = field("Имя")
        self.role    = field("Должность")
        self.age     = field("Возраст")
        self.stack   = section("Стек")
        self.sources = section("Источники")

    def save(self) -> None:
        lines = ["# Профиль пользователя", ""]
        if self.name:  lines.append(f"**Имя:** {self.name}")
        if self.role:  lines.append(f"**Должность:** {self.role}")
        if self.age:   lines.append(f"**Возраст:** {self.age}")
        if self.stack:
            lines += ["", "## Стек", self.stack]
        if self.sources:
            lines += ["", "## Источники", self.sources]
        with open(self._path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def exists(self) -> bool:
        return os.path.exists(self._path)

    def missing_fields(self) -> list[str]:
        mapping = {"name": "имя", "role": "должность",
                   "age": "возраст", "stack": "стек"}
        return [mapping[f] for f in self.REQUIRED if not getattr(self, f)]

    def to_prompt_block(self) -> str:
        lines = ["[ДОЛГОСРОЧНАЯ ПАМЯТЬ — профиль]"]
        if self.name:    lines.append(f"Имя: {self.name}")
        if self.role:    lines.append(f"Должность: {self.role}")
        if self.age:     lines.append(f"Возраст: {self.age}")
        if self.stack:   lines.append(f"Стек: {self.stack}")
        if self.sources: lines.append(f"Предпочтительные источники: {self.sources}")
        return "\n".join(lines)

    def summary(self) -> dict:
        return {
            "name":    self.name or "—",
            "role":    self.role or "—",
            "stack":   self.stack[:40] + "..." if len(self.stack) > 40 else self.stack or "—",
            "sources": bool(self.sources),
        }
