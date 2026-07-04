"""
Демо-скрипт для видео.

1. Пересчёт с нуля: удаляет results.json и results_plots/, заново прогоняет
   run_scenarios.py (2 длинных сценария) и visualize.py.
2. Живой мини-диалог: "вводит" несколько сообщений в одну сессию, показывая
   ответ + источники, память задачи (:state) и то, что цель не теряется.

Запуск: python demo.py
"""

import os
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

LIVE = [
    "I'm building a production RAG pipeline over research papers. My goal is to design it end to end. What chunking strategies should I consider?",
    "We'll fix fixed-size chunking with overlap. What re-ranking techniques exist in the post-retrieval stage?",
    ":state",
    "Remind me — what is our goal and what have we fixed so far?",
    "Now summarize the pipeline we've designed, consistent with our goal, and cite sources.",
]

TYPE_DELAY = 0.04
PAUSE = 2.0


def clean():
    print("Удаляю старые results.json и results_plots/...")
    rj = os.path.join(BASE, "results.json")
    if os.path.exists(rj):
        os.remove(rj)
    pd = os.path.join(BASE, "results_plots")
    if os.path.exists(pd):
        shutil.rmtree(pd)


def run_step(script: str):
    print(f"\n$ python {script}")
    subprocess.run([PY, os.path.join(BASE, script)], check=True, cwd=BASE)


def type_out(text: str):
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(TYPE_DELAY)
    sys.stdout.write("\n")
    sys.stdout.flush()


def main():
    print("=" * 70)
    print("ШАГ 1/2: ПРОГОН 2 СЦЕНАРИЕВ С НУЛЯ")
    print("=" * 70)
    clean()
    run_step("run_scenarios.py")
    run_step("visualize.py")

    import chat
    from cli import print_turn, print_state

    print("\n" + "=" * 70)
    print("ШАГ 2/2: ЖИВОЙ МИНИ-ДИАЛОГ — RAG + источники + память задачи")
    print("=" * 70)
    session = chat.ChatSession()

    for msg in LIVE:
        time.sleep(PAUSE)
        sys.stdout.write("\n> ")
        sys.stdout.flush()
        type_out(msg)
        if msg == ":state":
            print_state(session.task_state)
        else:
            print_turn(session.ask(msg))

    print("\nГотово. Графики в results_plots/, полный лог в results.json")


if __name__ == "__main__":
    main()
