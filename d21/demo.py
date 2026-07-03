"""
Демо-скрипт для видео.

1. Полностью пересобирает пайплайн с нуля: удаляет все производные артефакты
   (parsed/chunks/embeddings/index) и заново прогоняет
   extract.py -> chunking.py -> embed.py -> build_index.py.
   (Сырые PDF в data/raw и сама Ollama не трогаются — это окружение,
   а не результат пайплайна.)
2. Затем сам "вводит" заранее заданные вопросы в интерактивный поиск
   (имитация печати посимвольно с задержкой) и показывает top-3 из
   fixed и structure бок о бок — как в search.py, но без ручного набора.

Запуск: python demo.py
"""

import os
import shutil
import subprocess
import sys
import time

sys.stdout.reconfigure(line_buffering=True)  # иначе вывод дочерних subprocess обгоняет print()

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

PIPELINE_STEPS = ["extract.py", "chunking.py", "embed.py", "build_index.py"]

QUESTIONS = [
    "What is the difference between RAG-Sequence and RAG-Token models?",
    "How does chunking affect retrieval quality in RAG?",
    "What are the main challenges of naive RAG?",
]

TYPE_DELAY = 0.045    # сек. между символами при имитации печати
PAUSE_BEFORE = 1.0    # пауза перед началом ввода вопроса
PAUSE_AFTER = 3.0     # пауза после результатов (успеть прочитать на видео)


def clean_derived_data():
    print("Очищаю производные артефакты (parsed/chunks/embeddings/index)...")
    for d in ("parsed", "chunks", "embeddings", "index"):
        path = os.path.join(BASE, "data", d)
        if os.path.exists(path):
            shutil.rmtree(path)
    report = os.path.join(BASE, "data", "comparison_report.md")
    if os.path.exists(report):
        os.remove(report)


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
    print("ШАГ 1/2: ПЕРЕСБОРКА ПАЙПЛАЙНА С НУЛЯ")
    print("=" * 70)

    clean_derived_data()
    for step in PIPELINE_STEPS:
        run_step(step)

    # импортируем после сборки индекса — модуль их сразу читает с диска
    from search import embed_query, load_strategy, print_results
    from search import search as run_search

    idx_fixed, meta_fixed = load_strategy("fixed")
    idx_struct, meta_struct = load_strategy("structure")

    print("\n" + "=" * 70)
    print("ШАГ 2/2: ЖИВОЙ ПОИСК — fixed vs structure")
    print("=" * 70)

    for q in QUESTIONS:
        time.sleep(PAUSE_BEFORE)
        sys.stdout.write("\n> ")
        sys.stdout.flush()
        type_out(q)

        qvec = embed_query(q)
        print_results("FIXED", run_search(idx_fixed, meta_fixed, qvec))
        print_results("STRUCTURE", run_search(idx_struct, meta_struct, qvec))

        time.sleep(PAUSE_AFTER)

    print("\nГотово.")


if __name__ == "__main__":
    main()
