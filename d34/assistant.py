#!/usr/bin/env python3
"""CLI entry point for the goal-driven file assistant."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agent import FileAgent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-ассистент, который исследует и изменяет файлы проекта через MCP")
    parser.add_argument("project", type=Path, help="корень локального проекта")
    parser.add_argument(
        "goal",
        nargs="*",
        help="необязательная цель; без неё запускается интерактивный режим",
    )
    return parser.parse_args()


async def execute_goal(agent: FileAgent, project: Path, goal: str) -> bool:
    print(f"\nЦель: {goal}\nАссистент исследует файлы через MCP…\n")
    try:
        result = await agent.run(goal, project)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return False
    print(f"{result}\n")
    return True


async def run() -> int:
    args = parse_args()
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        print(f"Ошибка: каталог проекта не найден: {project}", file=sys.stderr)
        return 2
    agent = FileAgent()
    goal = " ".join(args.goal).strip()
    print(f"Проект: {project}")
    if goal:
        succeeded = await execute_goal(agent, project, goal)
        return 0 if succeeded else 1

    print("Интерактивный режим. Введите цель или /exit для завершения.")
    while True:
        try:
            goal = (await asyncio.to_thread(input, "d34> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи!")
            return 0
        if not goal:
            continue
        if goal in {"/exit", "/quit"}:
            print("До встречи!")
            return 0
        await execute_goal(agent, project, goal)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
