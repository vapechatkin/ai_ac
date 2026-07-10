"""d29: консольная визуализация сравнения до/после оптимизации."""

import json
import os

DATA = os.path.join(os.path.dirname(__file__), "results.json")

BLUE  = "\033[94m"
GREEN = "\033[92m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"

COLORS = {"before": "\033[91m", "after": "\033[92m"}   # красный / зелёный

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)

before = data["before"]
after  = data["after"]

W = 36  # ширина бара


def bar(value: float, max_val: float, color: str) -> str:
    filled = int(value / max_val * W) if max_val else 0
    return color + "█" * filled + DIM + "░" * (W - filled) + RESET


def winner(a, b, lower_is_better=True):
    if lower_is_better:
        return "after" if a >= b else "before"
    else:
        return "after" if a <= b else "before"


# ── Скорость ─────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*65}{RESET}")
print(f"{BOLD}  СКОРОСТЬ (среднее время на запрос){RESET}")
print(f"{'═'*65}")

max_t = max(before["avg_time"], after["avg_time"])
bt, at = before["avg_time"], after["avg_time"]
speedup = round(bt / at, 1) if at else "—"

print(f"\n  {COLORS['before']}До   {RESET} {bar(bt, max_t, COLORS['before'])} {COLORS['before']}{bt}s{RESET}")
print(f"  {COLORS['after']}После{RESET} {bar(at, max_t, COLORS['after'])} {COLORS['after']}{at}s{RESET}")
print(f"\n  {GREEN}{BOLD}После быстрее в {speedup}×{RESET}")

# ── Длина ответа ─────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*65}{RESET}")
print(f"{BOLD}  ДЛИНА ОТВЕТА (символов){RESET}")
print(f"{'═'*65}")

max_l = max(before["avg_len"], after["avg_len"])
bl, al = before["avg_len"], after["avg_len"]

print(f"\n  {COLORS['before']}До   {RESET} {bar(bl, max_l, COLORS['before'])} {COLORS['before']}{bl}c{RESET}")
print(f"  {COLORS['after']}После{RESET} {bar(al, max_l, COLORS['after'])} {COLORS['after']}{al}c{RESET}")
diff = round((bl - al) / bl * 100) if bl else 0
print(f"\n  {GREEN}{BOLD}После короче на {diff}%{RESET}  {DIM}(короче = конкретнее){RESET}")

# ── Качество формата ──────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*65}{RESET}")
print(f"{BOLD}  КАЧЕСТВО ФОРМАТА (0-3 балла){RESET}")
print(f"{DIM}  📖 заголовок + блок \"Похожие\" + 3 пункта{RESET}")
print(f"{'═'*65}")

max_f = 3.0
bf, af = before["avg_fmt"], after["avg_fmt"]

print(f"\n  {COLORS['before']}До   {RESET} {bar(bf, max_f, COLORS['before'])} {COLORS['before']}{bf}/3{RESET}")
print(f"  {COLORS['after']}После{RESET} {bar(af, max_f, COLORS['after'])} {COLORS['after']}{af}/3{RESET}")

# ── По запросам ───────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*65}{RESET}")
print(f"{BOLD}  ПО ЗАПРОСАМ{RESET}")
print(f"{'═'*65}")
print(f"  {'Запрос':<38} {'До':>6} {'После':>6}  {'Формат до':>9} {'Формат после':>12}")
print(f"  {'─'*38} {'─'*6} {'─'*6}  {'─'*9} {'─'*12}")

for b_r, a_r in zip(before["results"], after["results"]):
    q  = b_r["query"][:37]
    bt = f"{b_r['time']}s"
    at = f"{a_r['time']}s"
    bf = f"{b_r['format']}/3"
    af = f"{a_r['format']}/3"
    tc = GREEN if a_r["time"] < b_r["time"] else COLORS["before"]
    fc = GREEN if a_r["format"] >= b_r["format"] else COLORS["before"]
    print(f"  {q:<38} {COLORS['before']}{bt:>6}{RESET} {tc}{at:>6}{RESET}  "
          f"{COLORS['before']}{bf:>9}{RESET} {fc}{af:>12}{RESET}")

# ── Итог ─────────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*65}{RESET}")
print(f"{BOLD}  ИТОГ{RESET}")
print(f"{'═'*65}")
print(f"  Скорость:  {bt}s → {at}s  ({GREEN}{BOLD}×{speedup} быстрее{RESET})")
print(f"  Длина:     {bl}c → {al}c  ({GREEN}{BOLD}−{diff}%{RESET})")
print(f"  Формат:    {before['avg_fmt']}/3 → {after['avg_fmt']}/3  ({GREEN}{BOLD}+{round(after['avg_fmt']-before['avg_fmt'],1)} балла{RESET})")
print(f"{'═'*65}\n")
