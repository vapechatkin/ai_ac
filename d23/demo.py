"""
Демо-скрипт для видео.

1. Пересчитывает оценку с нуля: удаляет results.json и results_plots/,
   заново прогоняет run_eval.py (10 вопросов x 5 режимов) и visualize.py.
2. Затем сам "вводит" несколько живых вопросов, для каждого показывая
   контрастную пару режимов, иллюстрирующую один из трёх выводов README:
     - llm_rerank сужает top-10 до по-настоящему релевантных чанков
     - rewrite_filter иногда размывает точный запрос и портит retrieval
     - threshold защищает от вопроса вне корпуса (baseline вынужден бы
       использовать нерелевантный контекст, threshold честно говорит "не знаю")

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

LIVE_DEMOS = [
    ("What is the difference between RAG-Sequence and RAG-Token models?",
     ["baseline", "llm_rerank"]),
    ("What are the main challenges and future directions for RAG systems?",
     ["baseline", "rewrite_filter"]),
    ("What is the capital of France?",
     ["baseline", "threshold"]),
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
    print("ШАГ 1/2: ПЕРЕСЧЁТ ОЦЕНКИ (5 РЕЖИМОВ) С НУЛЯ")
    print("=" * 70)

    clean_results()
    run_step("run_eval.py")
    run_step("visualize.py")

    from cli import print_result
    import rag2

    print("\n" + "=" * 70)
    print("ШАГ 2/2: ЖИВОЙ ДИАЛОГ — контрастные пары режимов")
    print("=" * 70)

    for question, modes in LIVE_DEMOS:
        time.sleep(PAUSE_BEFORE)
        sys.stdout.write("\n> ")
        sys.stdout.flush()
        type_out(question)

        for mode in modes:
            print_result(mode.upper(), rag2.answer(question, mode))

        time.sleep(PAUSE_AFTER)

    print("\nГотово. Графики сравнения в results_plots/, полные ответы в results.json")


if __name__ == "__main__":
    main()
