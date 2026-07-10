"""d28: визуализация сравнения локальной и облачной RAG."""

import json
import os
import textwrap

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

DATA_FILE = os.path.join(os.path.dirname(__file__), "results.json")
OUT_DIR   = os.path.join(os.path.dirname(__file__), "results_plots")
os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA_FILE, encoding="utf-8") as f:
    results = json.load(f)

questions   = [r["question"] for r in results]
local_times = [r["local_time"] for r in results]
cloud_times = [r.get("cloud_time", 0) for r in results]

short_q = [textwrap.fill(q[:60], 30) for q in questions]
x = np.arange(len(questions))
w = 0.35

COLORS = {
    "local": "#5C85D6",
    "cloud": "#F4A442",
    "bg":    "#F8F9FA",
    "text":  "#2C2C2C",
}

# ── 1. Скорость ─────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(11, 5))
fig.patch.set_facecolor(COLORS["bg"])
ax.set_facecolor(COLORS["bg"])

bars_l = ax.bar(x - w/2, local_times, w, label=f"Local qwen2.5:3b  (avg {np.mean(local_times):.1f}s)",
                color=COLORS["local"], zorder=3)
bars_c = ax.bar(x + w/2, cloud_times, w, label=f"Cloud claude-haiku  (avg {np.mean(cloud_times):.1f}s)",
                color=COLORS["cloud"], zorder=3)

for bar in list(bars_l) + list(bars_c):
    h = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2, h + 0.15, f"{h:.1f}s",
            ha="center", va="bottom", fontsize=8, color=COLORS["text"])

ax.set_xticks(x)
ax.set_xticklabels(short_q, fontsize=8)
ax.set_ylabel("Время ответа (сек)", color=COLORS["text"])
ax.set_title("Скорость: локальная vs облачная модель", fontsize=13, color=COLORS["text"], pad=12)
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.spines[["top", "right"]].set_visible(False)

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "speed.png"), dpi=150)
plt.close()
print("saved: speed.png")


# ── 2. Длина ответа ──────────────────────────────────────────────────────────
local_lens = [len(r["answer_local"]) for r in results]
cloud_lens = [len(r.get("answer_cloud", "")) for r in results]

fig, ax = plt.subplots(figsize=(11, 5))
fig.patch.set_facecolor(COLORS["bg"])
ax.set_facecolor(COLORS["bg"])

bars_l = ax.bar(x - w/2, local_lens, w, label="Local", color=COLORS["local"], zorder=3)
bars_c = ax.bar(x + w/2, cloud_lens, w, label="Cloud", color=COLORS["cloud"], zorder=3)

ax.set_xticks(x)
ax.set_xticklabels(short_q, fontsize=8)
ax.set_ylabel("Длина ответа (символов)", color=COLORS["text"])
ax.set_title("Длина ответа: локальная vs облачная", fontsize=13, color=COLORS["text"], pad=12)
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3, zorder=0)
ax.spines[["top", "right"]].set_visible(False)

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "length.png"), dpi=150)
plt.close()
print("saved: length.png")


# ── 3. Сводная таблица ───────────────────────────────────────────────────────
fig = plt.figure(figsize=(13, 4.5))
fig.patch.set_facecolor(COLORS["bg"])

ax = fig.add_subplot(111)
ax.axis("off")

col_labels = ["Вопрос", "Local (s)", "Cloud (s)", "Быстрее", "Local len", "Cloud len"]
rows = []
for r in results:
    faster = "🏠 Local" if r["local_time"] < r.get("cloud_time", 9999) else "☁️  Cloud"
    rows.append([
        textwrap.fill(r["question"][:55], 40),
        f"{r['local_time']:.1f}",
        f"{r.get('cloud_time', '—'):.1f}" if r.get("cloud_time") else "—",
        faster,
        str(len(r["answer_local"])),
        str(len(r.get("answer_cloud", ""))),
    ])

# Итоговая строка
rows.append([
    "СРЕДНЕЕ",
    f"{np.mean(local_times):.1f}",
    f"{np.mean(cloud_times):.1f}",
    f"Cloud ×{np.mean(local_times)/np.mean(cloud_times):.1f} быстрее",
    f"{int(np.mean(local_lens))}",
    f"{int(np.mean(cloud_lens))}",
])

table = ax.table(cellText=rows, colLabels=col_labels,
                 loc="center", cellLoc="center")
table.auto_set_font_size(False)
table.set_fontsize(8.5)
table.scale(1, 2.0)

# Стили
for (row, col), cell in table.get_celld().items():
    cell.set_edgecolor("#D0D0D0")
    if row == 0:
        cell.set_facecolor("#3A3A5C")
        cell.set_text_props(color="white", fontweight="bold")
    elif row == len(rows):
        cell.set_facecolor("#E8EAF6")
        cell.set_text_props(fontweight="bold")
    elif row % 2 == 0:
        cell.set_facecolor("#FFFFFF")
    else:
        cell.set_facecolor(COLORS["bg"])

ax.set_title("Итоговое сравнение RAG: локальная vs облачная", fontsize=13,
             color=COLORS["text"], pad=16)

plt.tight_layout()
plt.savefig(os.path.join(OUT_DIR, "summary.png"), dpi=150, bbox_inches="tight")
plt.close()
print("saved: summary.png")

print(f"\nВсе графики → {OUT_DIR}/")
