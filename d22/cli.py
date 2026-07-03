"""
Интерактивный CLI: агент с двумя режимами.

Вводишь вопрос -> получаешь ответ без RAG и с RAG рядом, плюс источники,
использованные в RAG-режиме.

Команды:
  :rag <вопрос>     — ответить только в режиме RAG
  :norag <вопрос>   — ответить только без RAG
  <вопрос>          — по умолчанию оба режима сразу
  exit / quit       — выход
"""

import sys

import rag


def print_result(label: str, result: dict):
    print(f"\n--- {label} ---")
    print(result["text"])
    if result["retrieved"]:
        print("\nИсточники:")
        for r in result["retrieved"]:
            print(f"  score={r['score']:.3f} | {r['source']} | {r['section']}")


def main():
    print("Агент с двумя режимами (RAG / no-RAG). Индекс:", rag.STRATEGY)
    print("Введи вопрос (по умолчанию покажет оба режима), 'exit' — выход.\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("exit", "quit", "q"):
            break

        if line.startswith(":rag "):
            question = line[len(":rag "):].strip()
            print_result("RAG", rag.answer(question, "rag"))
        elif line.startswith(":norag "):
            question = line[len(":norag "):].strip()
            print_result("NO-RAG", rag.answer(question, "no_rag"))
        else:
            question = line
            print_result("NO-RAG", rag.answer(question, "no_rag"))
            print_result("RAG", rag.answer(question, "rag"))
        print()


if __name__ == "__main__":
    sys.exit(main())
