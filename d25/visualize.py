"""
Визуализация результатов run_scenarios.py из results.json.

results_plots/:
  summary.png        — по каждому сценарию: источники на knowledge-ходах,
                       удержание цели, воспроизведение памяти на memory-ходах
  memory_growth.png   — рост "памяти задачи" (clarified/constraints/glossary)
                       по ходам диалога, для обоих сценариев
"""

import json
import os

import matplotlib.pyplot as plt

BASE = os.path.dirname(os.path.abspath(__file__))
RESULTS_PATH = os.path.join(BASE, "results.json")
OUT_DIR = os.path.join(BASE, "results_plots")


def load():
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def plot_summary(results):
    metrics = [
        ("источники\n(knowledge)", "sources_on_knowledge_rate"),
        ("удержание\nцели", "goal_retention_rate"),
        ("память:\nцель", "memory_recall_rate"),
    ]
    labels = [m[0] for m in metrics]
    x = range(len(labels))
    width = 0.38
    colors = ["#2f7ed8", "#2ca02c"]

    fig, ax = plt.subplots(figsize=(9, 5))
    for si, r in enumerate(results):
        vals = [r["summary"][key] for _, key in metrics]
        offset = (si - 0.5) * width
        bars = ax.bar([xi + offset for xi in x], vals, width,
                      label=r["name"].split(".")[0], color=colors[si % 2])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v*100:.0f}%",
                    ha="center", fontsize=9)

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.15)
    ax.set_title("Мини-чат с RAG + памятью: проверки по 2 сценариям")
    ax.legend(loc="lower right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "summary.png"), dpi=150)
    plt.close(fig)


def plot_memory_growth(results):
    fig, axes = plt.subplots(1, len(results), figsize=(13, 5), sharey=True)
    if len(results) == 1:
        axes = [axes]

    for ax, r in zip(axes, results):
        turns = r["turns"]
        xs = [t["i"] for t in turns]
        ax.plot(xs, [t["n_clarified"] for t in turns], "-o", label="clarified", color="#2f7ed8")
        ax.plot(xs, [t["n_constraints"] for t in turns], "-s", label="constraints", color="#d62728")
        ax.plot(xs, [t["n_glossary"] for t in turns], "-^", label="glossary", color="#9467bd")
        # отметим memory-ходы
        for t in turns:
            if t["type"] == "memory":
                ax.axvline(t["i"], color="#cccccc", ls="--", alpha=0.7)
        ax.set_title(r["name"].split(".")[0] + ".")
        ax.set_xlabel("ход диалога (пунктир = memory-ход)")
        ax.set_xticks(xs)
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("накоплено элементов памяти")
    axes[0].legend(loc="upper left")
    fig.suptitle("Рост памяти задачи по ходу диалога")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "memory_growth.png"), dpi=150)
    plt.close(fig)


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"Нет {RESULTS_PATH}, сначала запусти run_scenarios.py")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    results = load()
    plot_summary(results)
    plot_memory_growth(results)
    print(f"Графики сохранены в {OUT_DIR}/:")
    for f in ("summary.png", "memory_growth.png"):
        print(f"  {f}")


if __name__ == "__main__":
    main()
