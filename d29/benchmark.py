"""
d29: оптимизация локальной LLM под технический Q&A.

Эксперименты:
  1. Temperature: 0.0 / 0.7 / 1.0
  2. Max tokens:  128 / 512 / 1024
  3. Системный промпт: generic / specialist
  4. Квантование/размер: qwen2.5:0.5b (Q4, 397MB) vs qwen2.5:3b (Q4, 1.9GB)
"""

import json
import os
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"

# Вопросы для технического Q&A
QUESTIONS = [
    "What is the difference between RAG-Sequence and RAG-Token?",
    "Explain vector embeddings in one paragraph.",
    "What is FAISS and why is it used for similarity search?",
]

# ── Системные промпты ────────────────────────────────────────────────────────
PROMPTS = {
    "generic": "You are a helpful assistant.",
    "specialist": (
        "You are a concise technical assistant specializing in AI and ML. "
        "Answer in 2-4 sentences. Be precise, avoid repetition. "
        "If you don't know — say so directly."
    ),
}


def call(model: str, system: str, question: str,
         temperature: float = 0.7, max_tokens: int = 512) -> dict:
    messages = [{"role": "user", "content": question}]
    body = {
        "model":   model,
        "messages": messages,
        "stream":  False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        body["messages"] = [{"role": "system", "content": system}] + messages

    t0 = time.time()
    resp = requests.post(OLLAMA_URL, json=body, timeout=120)
    resp.raise_for_status()
    elapsed = time.time() - t0
    text = resp.json()["message"]["content"].strip()
    return {"answer": text, "time": round(elapsed, 2), "len": len(text)}


def run_experiment(label: str, model: str, system: str,
                   temperature: float, max_tokens: int) -> dict:
    results = []
    for q in QUESTIONS:
        r = call(model, system, q, temperature, max_tokens)
        r["question"] = q
        results.append(r)
    avg_time = round(sum(r["time"] for r in results) / len(results), 2)
    avg_len  = int(sum(r["len"]  for r in results) / len(results))
    return {"label": label, "model": model, "temperature": temperature,
            "max_tokens": max_tokens, "avg_time": avg_time, "avg_len": avg_len,
            "results": results}


def bar(value: float, max_val: float, width: int = 30) -> str:
    filled = int(value / max_val * width) if max_val else 0
    return "█" * filled + "░" * (width - filled)


def print_results(experiments: list):
    max_time = max(e["avg_time"] for e in experiments)
    max_len  = max(e["avg_len"]  for e in experiments)

    print("\n" + "═" * 72)
    print("  РЕЗУЛЬТАТЫ ОПТИМИЗАЦИИ")
    print("═" * 72)
    print(f"  {'Эксперимент':<28} {'Время':>6}  {'Бар':30}  {'Длина':>6}")
    print("  " + "─" * 70)

    for e in experiments:
        b = bar(e["avg_time"], max_time)
        print(f"  {e['label']:<28} {e['avg_time']:>5.1f}s  {b}  {e['avg_len']:>5}c")

    print("═" * 72)

    # Победители
    fastest  = min(experiments, key=lambda e: e["avg_time"])
    best_len = min(experiments, key=lambda e: e["avg_len"])   # короче = concise
    print(f"\n  Быстрее всего:  {fastest['label']} ({fastest['avg_time']}s)")
    print(f"  Самый concise:  {best_len['label']} ({best_len['avg_len']} симв.)\n")

    # Пример ответа лучшего vs базового
    base = next(e for e in experiments if e["label"] == "baseline")
    best = next(e for e in experiments if e["label"] == "specialist+low_temp")
    q = QUESTIONS[0]
    bi = next(r for r in base["results"] if r["question"] == q)
    oi = next(r for r in best["results"] if r["question"] == q)

    print("═" * 72)
    print(f"  ПРИМЕР: {q}")
    print("─" * 72)
    print(f"  [baseline]  ({bi['time']}s, {bi['len']}c)\n  {bi['answer'][:300]}")
    print(f"\n  [optimized] ({oi['time']}s, {oi['len']}c)\n  {oi['answer'][:300]}")
    print("═" * 72 + "\n")


if __name__ == "__main__":
    experiments = []

    configs = [
        # label                   model           system_key    temp   tokens
        ("baseline",              "qwen2.5:3b",   "generic",    0.7,   512),
        ("low_temp (0.0)",        "qwen2.5:3b",   "generic",    0.0,   512),
        ("high_temp (1.0)",       "qwen2.5:3b",   "generic",    1.0,   512),
        ("short_output (128tok)", "qwen2.5:3b",   "generic",    0.7,   128),
        ("specialist",            "qwen2.5:3b",   "specialist", 0.7,   512),
        ("specialist+low_temp",   "qwen2.5:3b",   "specialist", 0.0,   512),
        ("small_model (0.5b)",    "qwen2.5:0.5b", "specialist", 0.0,   512),
    ]

    for label, model, sys_key, temp, tokens in configs:
        print(f"  Запускаю: {label}...", end=" ", flush=True)
        e = run_experiment(label, model, PROMPTS[sys_key], temp, tokens)
        experiments.append(e)
        print(f"{e['avg_time']}s")

    out = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(experiments, f, ensure_ascii=False, indent=2)

    print_results(experiments)
    print(f"  Результаты → {out}")
