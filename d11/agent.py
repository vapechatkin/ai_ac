# agent.py
#
# Агент с явной моделью памяти.
#
# Старт сессии:
#   1. Загружает все три слоя памяти.
#   2. Если LTM отсутствует или неполная — спрашивает пользователя.
#   3. Если в WM есть незавершённые задачи — предлагает продолжить.
#   4. Строит system prompt из всех слоёв.
#
# Каждый ход:
#   - STM обновляется через LLM-экстракцию (проблема + решения).
#   - WM обновляется явными вызовами add_done().
#
# Конец сессии (end_session):
#   - STM очищается.
#   - WM сохраняется.
#   - LTM остаётся без изменений (если пользователь не попросил обновить).

import os

import anthropic
from dotenv import load_dotenv

from memory import LongTermMemory, ShortTermMemory, WorkingMemory

load_dotenv()

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")

MODEL     = "claude-haiku-4-5"
PRICE_IN  = 1.00 / 1_000_000
PRICE_OUT = 5.00 / 1_000_000

SYSTEM_BASE = (
    "Ты полезный AI-ассистент. "
    "Учитывай всю предоставленную тебе информацию о пользователе, задаче и текущем диалоге. "
    "Обращайся к пользователю по имени. Отвечай кратко и по делу."
)

STM_EXTRACT_PROMPT = """\
Из диалога ниже извлеки:
1. Основную проблему/вопрос пользователя (одно предложение).
2. Предложенные решения с аргументами (список, максимум 4).

Верни ТОЛЬКО валидный JSON в формате:
{
  "problem": "...",
  "solutions": [
    {"solution": "...", "arguments": "..."},
    ...
  ]
}

Если решений ещё нет — solutions = [].
Если проблема не определена — problem = "".
Отвечай ТОЛЬКО JSON, без пояснений."""


def _ask_input(prompt: str, default: str = "") -> str:
    """Запрашивает ввод у пользователя в терминале."""
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"  {prompt}{suffix}: ").strip()
        return value or default
    except (EOFError, KeyboardInterrupt):
        return default


class MemoryAgent:

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=_api_key)
        self.stm    = ShortTermMemory()
        self.wm     = WorkingMemory()
        self.ltm    = LongTermMemory()

        self._messages: list[dict] = []   # буфер для STM-экстракции
        self.total_input_tokens  = 0
        self.total_output_tokens = 0
        self.turn_count          = 0

    # ─────────────────────────────────── запуск сессии

    def start_session(self) -> None:
        """
        Главный метод инициализации.
        Вызывается один раз перед началом диалога.
        """
        print("\n" + "═" * 58)
        print("  ЗАПУСК СЕССИИ")
        print("═" * 58)

        self._init_ltm()
        self._init_wm()

        system = self._build_system_prompt()
        print("\n  [SYSTEM PROMPT сформирован]")
        print("─" * 58)
        print(system)
        print("─" * 58 + "\n")

    def _init_ltm(self) -> None:
        """Проверяет LTM. Если отсутствует или неполная — собирает данные у пользователя."""
        missing = self.ltm.missing_fields()

        if not missing:
            print(f"\n  [LTM] Профиль загружен: {self.ltm.name}, {self.ltm.role}")
            return

        if not self.ltm.exists():
            print("\n  [LTM] Профиль не найден. Заполним сейчас.")
        else:
            print(f"\n  [LTM] Профиль неполный. Не хватает: {', '.join(missing)}")

        print()
        if not self.ltm.name:
            self.ltm.name = _ask_input("Ваше имя")
        if not self.ltm.role:
            self.ltm.role = _ask_input("Должность / роль")
        if not self.ltm.age:
            self.ltm.age = _ask_input("Возраст (Enter — пропустить)")
        if not self.ltm.stack:
            self.ltm.stack = _ask_input("Основной стек технологий")
        if not self.ltm.sources:
            self.ltm.sources = _ask_input(
                "Предпочтительные источники информации (Enter — пропустить)"
            )

        self.ltm.save()
        print(f"\n  [LTM] Профиль сохранён → {self.ltm._path}")

    def _init_wm(self) -> None:
        """
        Проверяет рабочую память.
        Если есть незавершённые задачи — предлагает продолжить.
        """
        open_tasks = [name for name, info in self.wm.tasks.items()
                      if info["status"] != "завершена"]

        if not open_tasks:
            print("\n  [WM] Незавершённых задач нет.")
            self._start_new_task_dialog()
            return

        print(f"\n  [WM] Найдены незавершённые задачи ({len(open_tasks)}):")
        for i, name in enumerate(open_tasks, 1):
            info = self.wm.tasks[name]
            done_count = len(info["done"])
            print(f"    {i}. {name}  [{done_count} шаг(ов) выполнено]")

        print()
        choice = _ask_input(
            "Продолжить задачу (введи номер) или начать новую (Enter)"
        )

        if choice.isdigit() and 1 <= int(choice) <= len(open_tasks):
            task_name = open_tasks[int(choice) - 1]
            self.wm.resume_task(task_name)
            print(f"  [WM] Продолжаем задачу «{task_name}»")
        else:
            self._start_new_task_dialog()

    def _start_new_task_dialog(self) -> None:
        name = _ask_input("Название новой задачи", default="Без названия")
        self.wm.new_task(name)
        print(f"  [WM] Новая задача: «{name}»")

    # ─────────────────────────────────── system prompt

    def _build_system_prompt(self) -> str:
        blocks = [SYSTEM_BASE]

        ltm_block = self.ltm.to_prompt_block()
        if ltm_block:
            blocks.append(ltm_block)

        wm_block = self.wm.current_task_block()
        if wm_block:
            blocks.append(wm_block)

        stm_block = self.stm.to_prompt_block()
        if stm_block:
            blocks.append(stm_block)

        return "\n\n".join(blocks)

    # ─────────────────────────────────── STM-экстракция

    def _update_stm(self) -> None:
        """
        После каждого хода просит модель извлечь проблему и решения из буфера.
        Обновляет STM и сохраняет в файл.
        """
        if len(self._messages) < 2:
            return

        dialog_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in self._messages[-6:]
        )

        try:
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=STM_EXTRACT_PROMPT,
                messages=[{"role": "user", "content": dialog_text}],
            )
            import json, re
            raw = resp.content[0].text.strip()
            # Вырезаем JSON если модель добавила текст вокруг
            # Убираем ```json ... ``` если модель завернула ответ в code block
            raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(match.group()) if match else {}
            problem   = data.get("problem") or self.stm.problem
            solutions = data.get("solutions") or self.stm.solutions
            if not problem:
                user_msgs = [msg["content"] for msg in self._messages if msg["role"] == "user"]
                problem = user_msgs[-1] if user_msgs else ""
            self.stm.update(problem=problem, solutions=solutions)
        except Exception:
            pass  # экстракция не критична, продолжаем

    # ─────────────────────────────────── основной запрос

    def ask(self, user_message: str) -> tuple[str, dict]:
        self.turn_count += 1

        self._messages.append({"role": "user", "content": user_message})

        system   = self._build_system_prompt()
        messages = list(self._messages)

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system,
            messages=messages,
        )

        answer     = response.content[0].text.strip()
        inp_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens

        self.total_input_tokens  += inp_tokens
        self.total_output_tokens += out_tokens

        self._messages.append({"role": "assistant", "content": answer})

        # Обновляем STM после каждого хода
        self._update_stm()

        stats = {
            "turn":       self.turn_count,
            "inp_tokens": inp_tokens,
            "out_tokens": out_tokens,
            "cost":       (self.total_input_tokens  * PRICE_IN +
                           self.total_output_tokens * PRICE_OUT),
        }
        return answer, stats

    # ─────────────────────────────────── конец сессии

    def end_session(self) -> None:
        """
        Завершает сессию:
        - STM очищается
        - WM сохраняется
        - LTM остаётся (если пользователь не попросил обновить)
        """
        print("\n" + "═" * 58)
        print("  ЗАВЕРШЕНИЕ СЕССИИ")
        print("═" * 58)

        if not self.stm.is_empty():
            print(f"\n  [STM] Финальное саммари:")
            print(f"    Проблема: {self.stm.problem}")
            for s in self.stm.solutions:
                print(f"    • {s['solution']}")

        print(f"  [STM] Сохранена в {self.stm._path}")
        print(f"  ⚠️  Сессия завершена. Введите /clear-stm чтобы очистить краткосрочную память.")

        self.wm.save()
        print(f"  [WM]  Сохранена. Текущая задача: «{self.wm.current_task or '—'}»")

        print(f"  [LTM] Без изменений ({self.ltm._path})")

        cost = self.total_input_tokens * PRICE_IN + self.total_output_tokens * PRICE_OUT
        print(f"\n  Итого: {self.turn_count} ходов | "
              f"вход {self.total_input_tokens:,} + выход {self.total_output_tokens:,} tok | "
              f"${cost:.5f}")
        print("═" * 58 + "\n")

    # ─────────────────────────────────── явное управление WM

    def task_done(self, item: str) -> None:
        self.wm.add_done(item)
        print(f"  [WM] ✓ {item}")

    def close_task(self) -> None:
        self.wm.close_task()

    def update_profile(self) -> None:
        """Обновляет LTM по запросу пользователя."""
        print("\n  [LTM] Обновление профиля:")
        self.ltm.name    = _ask_input("Имя",        self.ltm.name)
        self.ltm.role    = _ask_input("Должность",  self.ltm.role)
        self.ltm.age     = _ask_input("Возраст",    self.ltm.age)
        self.ltm.stack   = _ask_input("Стек",       self.ltm.stack)
        self.ltm.sources = _ask_input("Источники",  self.ltm.sources)
        self.ltm.save()
        print(f"  [LTM] Профиль обновлён → {self.ltm._path}\n")
