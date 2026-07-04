"""
Интерактивный CLI для grounded-RAG: на каждый вопрос показывает
ответ + источники + цитаты, либо режим "не знаю" при слабом контексте.

Запуск: python cli.py
"""

import sys

import rag3


def print_result(result: dict):
    if result["idk"]:
        print(f"\n[НЕ ЗНАЮ — {result['idk_reason']}]")
        print(result["answer"])
        if result["idk_reason"] == "below_threshold":
            top = max((c["score"] for c in result["retrieved"]), default=0.0)
            print(f"(лучший скор {top:.3f} < порога {rag3.SIM_THRESHOLD})")
        return

    print("\nОТВЕТ:")
    print(result["answer"])

    print("\nИСТОЧНИКИ:")
    for s in result["sources"]:
        print(f"  - {s['source']} | {s['section']} | {s['chunk_id']}")

    print("\nЦИТАТЫ:")
    for c in result["citations"]:
        print(f"  - [{c['chunk_id']}] \"{c['quote']}\"")


def main():
    print("Grounded RAG: ответ + источники + цитаты, режим 'не знаю' при слабом контексте.")
    print("Ввод: вопрос | exit\n")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line or line.lower() in ("exit", "quit", "q"):
            break
        print_result(rag3.answer(line))
        print()


if __name__ == "__main__":
    sys.exit(main())
