"""
Визуализация сравнения 5 режимов (no_rag, baseline, threshold, llm_rerank,
rewrite_filter) из results.json (run_eval.py).

Сохраняет в results_plots/:
  summary.png       — средние keyword_coverage / source_hit / section_hit по режимам
  per_question.png   — keyword_coverage по каждому из 10 вопросов, все режимы
  kept_chunks.png     — сколько чанков в среднем остаётся после фильтрации (топ-K до/после)
"""

import json
import os

import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(BASE, "results.json")
OUT_DIR = os.path.join(BASE, "results_plots")

MODES = ["no_rag", "baseline", "threshold", "llm_rerank", "rewrite_filter"]
COLORS = {
    "no_rag": "#888888", "baseline": "#2f7ed8", "threshold": "#2ca02c",
    "llm_rerank": "#d62728", "rewrite_filter": "#9467bd",
}


def load_results():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def plot_summary(results):
    n = len(results)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    avg_cov = [sum(r["modes"][m]["keyword_coverage"] for r in results) / n for m in MODES]
    axes[0].bar(MODES, avg_cov, color=[COLORS[m] for m in MODES])
    axes[0].set_title("keyword coverage (среднее)")
    axes[0].set_ylim(0, 1.1)
    axes[0].tick_params(axis="x", rotation=30)

    rag_modes = MODES[1:]
    src_rate = [sum(r["modes"][m]["source_hit"] for r in results) / n for m in rag_modes]
    axes[1].bar(rag_modes, src_rate, color=[COLORS[m] for m in rag_modes])
    axes[1].set_title("source hit rate")
    axes[1].set_ylim(0, 1.1)
    axes[1].tick_params(axis="x", rotation=30)

    sec_rate = [sum(r["modes"][m]["section_hit"] for r in results) / n for m in rag_modes]
    axes[2].bar(rag_modes, sec_rate, color=[COLORS[m] for m in rag_modes])
    axes[2].set_title("section hit rate")
    axes[2].set_ylim(0, 1.1)
    axes[2].tick_params(axis="x", rotation=30)

    for ax in axes:
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Сводные метрики: no-RAG vs 4 режима RAG (10 вопросов)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "summary.png"), dpi=150)
    plt.close(fig)


def plot_per_question(results):
    ids = [r["id"] for r in results]
    x = range(len(ids))
    width = 0.15

    fig, ax = plt.subplots(figsize=(13, 5))
    for i, mode in enumerate(MODES):
        values = [r["modes"][mode]["keyword_coverage"] for r in results]
        offset = (i - (len(MODES) - 1) / 2) * width
        ax.bar([xi + offset for xi in x], values, width, label=mode, color=COLORS[mode])

    ax.set_xticks(list(x))
    ax.set_xticklabels([f"Q{i}" for i in ids])
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("keyword coverage")
    ax.set_title("keyword coverage по вопросам, все режимы")
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "per_question.png"), dpi=150)
    plt.close(fig)


def plot_kept_chunks(results):
    rag_modes = MODES[1:]
    n = len(results)
    avg_retrieved = [sum(r["modes"][m]["n_retrieved"] for r in results) / n for m in rag_modes]
    avg_kept = [sum(r["modes"][m]["n_kept"] for r in results) / n for m in rag_modes]

    x = range(len(rag_modes))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - width / 2 for i in x], avg_retrieved, width, label="top-K до фильтра", color="#cccccc")
    ax.bar([i + width / 2 for i in x], avg_kept, width, label="top-K после фильтра", color="#2f7ed8")

    ax.set_xticks(list(x))
    ax.set_xticklabels(rag_modes)
    ax.set_ylabel("среднее число чанков")
    ax.set_title("Топ-K до/после фильтрации по режимам")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "kept_chunks.png"), dpi=150)
    plt.close(fig)


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"Нет {RESULTS_PATH}, сначала запусти run_eval.py")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    results = load_results()

    plot_summary(results)
    plot_per_question(results)
    plot_kept_chunks(results)

    print(f"Графики сохранены в {OUT_DIR}/:")
    for fname in ("summary.png", "per_question.png", "kept_chunks.png"):
        print(f"  {fname}")


if __name__ == "__main__":
    main()
