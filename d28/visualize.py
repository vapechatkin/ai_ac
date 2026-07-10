"""d28: визуализация сравнения RAG в консоли."""

import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), "results.json")

with open(DATA_FILE, encoding="utf-8") as f:
    results = json.load(f)

LOCAL_COLOR = "\033[94m"   # синий
CLOUD_COLOR = "\033[93m"   # жёлтый
BOLD        = "\033[1m"
RESET       = "\033[0m"
GREEN       = "\033[92m"
DIM         = "\033[2m"

BAR_WIDTH = 40


def bar(value: float, max_val: float, color: str) -> str:
    filled = int(value / max_val * BAR_WIDTH)
    return color + "█" * filled + DIM + "░" * (BAR_WIDTH - filled) + RESET


def short(text: str, n: int = 45) -> str:
    return text[:n] + "…" if len(text) > n else text


max_time = max(max(r["local_time"], r.get("cloud_time", 0)) for r in results)
max_len  = max(max(len(r["answer_local"]), len(r.get("answer_cloud", ""))) for r in results)

# ── Скорость ─────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  СКОРОСТЬ ОТВЕТА (секунды){RESET}")
print(f"{'═'*70}{RESET}")

for r in results:
    q = short(r["question"])
    lt = r["local_time"]
    ct = r.get("cloud_time", 0)
    print(f"\n  {DIM}{q}{RESET}")
    print(f"  Local  {bar(lt, max_time, LOCAL_COLOR)} {LOCAL_COLOR}{lt:.1f}s{RESET}")
    print(f"  Cloud  {bar(ct, max_time, CLOUD_COLOR)} {CLOUD_COLOR}{ct:.1f}s{RESET}")

avg_l = sum(r["local_time"] for r in results) / len(results)
avg_c = sum(r.get("cloud_time", 0) for r in results) / len(results)
print(f"\n  {BOLD}Среднее:  Local {avg_l:.1f}s   Cloud {avg_c:.1f}s   "
      f"({GREEN}Cloud ×{avg_l/avg_c:.1f} быстрее{RESET}{BOLD}){RESET}")

# ── Длина ответа ─────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  ДЛИНА ОТВЕТА (символов){RESET}")
print(f"{'═'*70}{RESET}")

for r in results:
    q = short(r["question"])
    ll = len(r["answer_local"])
    cl = len(r.get("answer_cloud", ""))
    print(f"\n  {DIM}{q}{RESET}")
    print(f"  Local  {bar(ll, max_len, LOCAL_COLOR)} {LOCAL_COLOR}{ll}{RESET}")
    print(f"  Cloud  {bar(cl, max_len, CLOUD_COLOR)} {CLOUD_COLOR}{cl}{RESET}")

avg_ll = sum(len(r["answer_local"]) for r in results) / len(results)
avg_cl = sum(len(r.get("answer_cloud", "")) for r in results) / len(results)
print(f"\n  {BOLD}Среднее:  Local {int(avg_ll)} симв.   Cloud {int(avg_cl)} симв.{RESET}")

# ── Итоговая таблица ─────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*70}{RESET}")
print(f"{BOLD}  ИТОГО{RESET}")
print(f"{'═'*70}")
print(f"  {'Вопрос':<46} {'Local':>6} {'Cloud':>6}  Быстрее")
print(f"  {'─'*46} {'─'*6} {'─'*6}  {'─'*7}")

for r in results:
    q  = short(r["question"], 46)
    lt = r["local_time"]
    ct = r.get("cloud_time", 0)
    winner = f"{GREEN}Cloud{RESET}" if ct < lt else f"{LOCAL_COLOR}Local{RESET}"
    print(f"  {q:<46} {LOCAL_COLOR}{lt:>5.1f}s{RESET} {CLOUD_COLOR}{ct:>5.1f}s{RESET}  {winner}")

print(f"\n  {BOLD}{'СРЕДНЕЕ':<46} {avg_l:>5.1f}s {avg_c:>6.1f}s  "
      f"{GREEN}Cloud ×{avg_l/avg_c:.1f}{RESET}{BOLD}{RESET}")
print(f"{'═'*70}\n")
