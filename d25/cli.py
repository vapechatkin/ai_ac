"""
Интерактивный мини-чат с RAG + памятью задачи.

На каждый вопрос: ищет контекст в базе, отвечает с учётом памяти задачи и
истории, выводит источники. Команды:
  :state  — показать текущую память задачи (goal / clarified / constraints /
            glossary / open_questions)
  exit    — выход

Запуск: python cli.py
"""

import json
import sys

import chat


def print_turn(turn: dict):
    if turn["idk"]:
        print(f"\n[НЕ ЗНАЮ] {turn['answer']}")
        return
    print(f"\nАССИСТЕНТ: {turn['answer']}")
    if turn["sources"]:
        print("\nИСТОЧНИКИ:")
        for s in turn["sources"]:
            print(f"  - {s['source']} | {s['section']} | {s['chunk_id']}")
    else:
        print("\n(ответ из памяти задачи, без обращения к базе)")


def print_state(state: dict):
    print("\n=== ПАМЯТЬ ЗАДАЧИ ===")
    print(f"Цель: {state['goal']}")
    for key, label in (("clarified", "Уточнено"), ("constraints", "Ограничения"),
                       ("open_questions", "Открытые вопросы")):
        if state[key]:
            print(f"{label}:")
            for x in state[key]:
                print(f"  - {x}")
    if state["glossary"]:
        print("Термины:")
        for g in state["glossary"]:
            print(f"  - {g['term']}: {g['definition']}")


def main():
    print("Мини-чат с RAG + памятью задачи. Команды: :state | exit\n")
    session = chat.ChatSession()

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("exit", "quit", "q"):
            break
        if line.lower() == ":state":
            print_state(session.task_state)
            print()
            continue
        print_turn(session.ask(line))
        print()


if __name__ == "__main__":
    sys.exit(main())
