"""
Визуализация проверки grounded-RAG из results.json (run_eval.py).

Сохраняет в results_plots/:
  checks.png        — три обязательные проверки (источники / цитаты /
                      смысл==цитаты) + режим "не знаю", сводно
  per_question.png   — по каждому из 10 вопросов: есть источники, есть цитаты,
                      faithful, доля дословных цитат, режим idk
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


def plot_checks(data):
    s = data["summary"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # слева: обязательные проверки среди отвеченных вопросов
    labels = ["источники", "цитаты", "смысл==\nцитаты", "цитаты\nдословно"]
    values = [
        s["answered_sources_rate"], s["answered_citations_rate"],
        s["answered_matches_citations_rate"], s["answered_citations_grounded_avg"],
    ]
    colors = ["#2f7ed8", "#2ca02c", "#9467bd", "#8c8c8c"]
    bars = axes[0].bar(labels, values, color=colors)
    axes[0].set_ylim(0, 1.15)
    axes[0].set_title(f"Обязательные проверки (среди {s['n_answered']} отвеченных)")
    axes[0].grid(axis="y", alpha=0.3)
    for b, v in zip(bars, values):
        axes[0].text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v*100:.0f}%",
                     ha="center", fontsize=10)

    # справа: режим "не знаю"
    idk_labels = ["по теме\n(отвечено)", "по теме\n(не знаю)", "вне корпуса\n(не знаю)"]
    idk_vals = [s["n_answered"], s["n_idk"], s["off_topic_idk"]]
    idk_colors = ["#2ca02c", "#d62728", "#d62728"]
    bars2 = axes[1].bar(idk_labels, idk_vals, color=idk_colors)
    axes[1].set_title("Режим 'не знаю': слабый контекст -> отказ")
    axes[1].set_ylabel("число вопросов")
    axes[1].grid(axis="y", alpha=0.3)
    for b, v in zip(bars2, idk_vals):
        axes[1].text(b.get_x() + b.get_width() / 2, v + 0.05, str(v),
                     ha="center", fontsize=11)

    fig.suptitle("Grounded RAG: обязательные источники+цитаты и режим 'не знаю'")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "checks.png"), dpi=150)
    plt.close(fig)


def plot_per_question(data):
    rows = data["on_topic"]
    ids = [f"Q{r['id']}" for r in rows]
    x = range(len(ids))
    width = 0.2

    has_src = [1 if r["has_sources"] else 0 for r in rows]
    has_cite = [1 if r["has_citations"] else 0 for r in rows]
    faithful = [1 if r["answer_matches_citations"] else 0 for r in rows]
    grounded = [r["citations_grounded"] for r in rows]

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.bar([xi - 1.5 * width for xi in x], has_src, width, label="есть источники", color="#2f7ed8")
    ax.bar([xi - 0.5 * width for xi in x], has_cite, width, label="есть цитаты", color="#2ca02c")
    ax.bar([xi + 0.5 * width for xi in x], faithful, width, label="смысл==цитаты", color="#9467bd")
    ax.bar([xi + 1.5 * width for xi in x], grounded, width, label="доля дословных цитат", color="#cccccc")

    for i, r in enumerate(rows):
        if r["idk"]:
            ax.text(i, 1.05, "не знаю", ha="center", color="#d62728", fontsize=8, rotation=0)

    ax.set_xticks(list(x))
    ax.set_xticklabels(ids)
    ax.set_ylim(0, 1.2)
    ax.set_title("По вопросам: источники / цитаты / смысл==цитаты / дословность")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, "per_question.png"), dpi=150)
    plt.close(fig)


def main():
    if not os.path.exists(RESULTS_PATH):
        print(f"Нет {RESULTS_PATH}, сначала запусти run_eval.py")
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    data = load_results()

    plot_checks(data)
    plot_per_question(data)

    print(f"Графики сохранены в {OUT_DIR}/:")
    for fname in ("checks.png", "per_question.png"):
        print(f"  {fname}")


if __name__ == "__main__":
    main()
