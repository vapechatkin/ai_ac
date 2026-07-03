"""
Визуализация результатов сравнения RAG vs no-RAG (results.json из run_eval.py).

Строит и сохраняет в results_plots/:
  1. per_question.png   — keyword coverage по каждому из 10 вопросов, RAG vs no-RAG
  2. summary.png        — средние метрики: keyword coverage (оба режима),
                           source hit rate, section hit rate (только RAG)
  3. latency.png         — время ответа по вопросам, RAG vs no-RAG
"""

import json
import os

import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(BASE, "results.json")
OUT_DIR = os.path.join(BASE, "results_plots")


def load_results():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def plot_per_question(results):
    ids = [r["id"] for r in results]
    no_rag = [r["no_rag"]["keyword_coverage"] for r in results]
    rag_ = [r["rag"]["keyword_coverage"] for r in results]

    x = range(len(ids))
    width = 0.35

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([i - width / 2 for i in x], no_rag, width, label="no-RAG", color="#888888")
    ax.bar([i + width / 2 for i in x], rag_, width, label="RAG", color="#2f7ed8")

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{i}" for i in ids])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("keyword coverage (доля ожидаемых фактов в ответе)")
    ax.set_title("RAG vs no-RAG: keyword coverage по вопросам")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "per_question.png"), dpi=150)
    plt.close(fig)


def plot_summary(results):
    n = len(results)
    avg_no_rag = sum(r["no_rag"]["keyword_coverage"] for r in results) / n
    avg_rag = sum(r["rag"]["keyword_coverage"] for r in results) / n
    source_hit_rate = sum(r["rag"]["source_hit"] for r in results) / n
    section_hit_rate = sum(r["rag"]["section_hit"] for r in results) / n

    labels = ["keyword coverage\n(no-RAG)", "keyword coverage\n(RAG)",
              "source hit rate\n(RAG)", "section hit rate\n(RAG)"]
    values = [avg_no_rag, avg_rag, source_hit_rate, section_hit_rate]
    colors = ["#888888", "#2f7ed8", "#2ca02c", "#2ca02c"]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, values, color=colors)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center")
    ax.set_ylim(0, 1.15)
    ax.set_title("Сводные метрики по 10 контрольным вопросам")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "summary.png"), dpi=150)
    plt.close(fig)


def plot_latency(results):
    ids = [r["id"] for r in results]
    no_rag = [r["no_rag"]["latency_sec"] for r in results]
    rag_ = [r["rag"]["latency_sec"] for r in results]

    x = range(len(ids))
    width = 0.35

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar([i - width / 2 for i in x], no_rag, width, label="no-RAG", color="#888888")
    ax.bar([i + width / 2 for i in x], rag_, width, label="RAG", color="#2f7ed8")

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{i}" for i in ids])
    ax.set_ylabel("время ответа, сек (retrieval + LLM)")
    ax.set_title("RAG vs no-RAG: latency по вопросам")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "latency.png"), dpi=150)
    plt.close(fig)


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"Нет {RESULTS_PATH}, сначала запусти run_eval.py")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    results = load_results()

    plot_per_question(results)
    plot_summary(results)
    plot_latency(results)

    print(f"Графики сохранены в {OUT_DIR}/:")
    for fname in ("per_question.png", "summary.png", "latency.png"):
        print(f"  {fname}")


if __name__ == "__main__":
    main()
