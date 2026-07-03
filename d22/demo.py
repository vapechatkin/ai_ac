"""
Демо-скрипт для видео.

1. Пересчитывает оценку с нуля: удаляет results.json и results_plots/,
   заново прогоняет run_eval.py (10 вопросов x 2 режима через Claude API)
   и visualize.py (графики).
2. Затем сам "вводит" несколько живых вопросов (имитация печати посимвольно)
   и показывает ответ без RAG и с RAG рядом, как в cli.py — специально
   подобраны разные случаи: где RAG уверенно выигрывает, и где retrieval
   промахивается мимо нужного чанка (честное ограничение, разобрано в README).

Запуск: python demo.py
"""

import os
import subprocess
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

LIVE_QUESTIONS = [
    "What are the main challenges and future directions for RAG systems?",
    "What retriever and generator components does the original RAG paper (Lewis et al.) use?",
    "What is the difference between RAG-Sequence and RAG-Token models?",
]

TYPE_DELAY = 0.045
PAUSE_BEFORE = 1.0
PAUSE_AFTER = 3.0


def clean_results():
    print("Удаляю старые results.json и results_plots/...")
    results_json = os.path.join(BASE, "results.json")
    if os.path.exists(results_json):
        os.remove(results_json)
    plots_dir = os.path.join(BASE, "results_plots")
    if os.path.exists(plots_dir):
        import shutil
        shutil.rmtree(plots_dir)


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
    print("ШАГ 1/2: ПЕРЕСЧЁТ ОЦЕНКИ RAG vs no-RAG С НУЛЯ")
    print("=" * 70)

    clean_results()
    run_step("run_eval.py")
    run_step("visualize.py")

    from cli import print_result
    import rag

    print("\n" + "=" * 70)
    print("ШАГ 2/2: ЖИВОЙ ДИАЛОГ С АГЕНТОМ — no-RAG vs RAG")
    print("=" * 70)

    for q in LIVE_QUESTIONS:
        time.sleep(PAUSE_BEFORE)
        sys.stdout.write("\n> ")
        sys.stdout.flush()
        type_out(q)

        print_result("NO-RAG", rag.answer(q, "no_rag"))
        print_result("RAG", rag.answer(q, "rag"))

        time.sleep(PAUSE_AFTER)

    print("\nГотово. Графики сравнения в results_plots/, полные ответы в results.json")


if __name__ == "__main__":
    main()
