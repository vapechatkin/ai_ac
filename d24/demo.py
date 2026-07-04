"""
Демо-скрипт для видео.

1. Пересчитывает проверку с нуля: удаляет results.json и results_plots/,
   заново прогоняет run_eval.py (10 вопросов + вопросы вне корпуса) и
   visualize.py.
2. Затем "вводит" несколько живых вопросов, показывая для каждого
   ответ + источники + цитаты, а также режим "не знаю":
     - обычный вопрос по теме -> ответ с источниками и цитатами
     - вопрос, для которого в корпусе нет конкретики -> честный отказ
     - вопрос вообще не по теме -> "не знаю" по порогу релевантности

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
    "What is the difference between RAG-Sequence and RAG-Token models?",
    "What retriever and generator components does the original RAG paper (Lewis et al.) use?",
    "What is the capital of France?",
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
    print("ШАГ 1/2: ПЕРЕСЧЁТ ПРОВЕРКИ (10 ВОПРОСОВ + ВНЕ КОРПУСА) С НУЛЯ")
    print("=" * 70)

    clean_results()
    run_step("run_eval.py")
    run_step("visualize.py")

    from cli import print_result
    import rag3

    print("\n" + "=" * 70)
    print("ШАГ 2/2: ЖИВОЙ ДИАЛОГ — источники, цитаты и режим 'не знаю'")
    print("=" * 70)

    for question in LIVE_DEMOS:
        time.sleep(PAUSE_BEFORE)
        sys.stdout.write("\n> ")
        sys.stdout.flush()
        type_out(question)
        print_result(rag3.answer(question))
        time.sleep(PAUSE_AFTER)

    print("\nГотово. Графики в results_plots/, полные ответы в results.json")


if __name__ == "__main__":
    main()
