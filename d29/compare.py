"""
d29: сравнение до/после оптимизации агента-рекомендатора книг.

До:  generic prompt, temperature=0.7, max_tokens=512, no context
После: specialist prompt, temperature=0.8, max_tokens=400, num_ctx=8192
"""

import json
import os
import time

import requests

URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5:3b"

QUERIES = [
    "хочу детектив с неожиданной развязкой",
    "что-нибудь про путешествия и самопознание",
    "научная фантастика про искусственный интеллект",
    "классика про войну и человеческую природу",
]

# ── Конфиги ──────────────────────────────────────────────────────────────────
CONFIGS = {
    "before": {
        "label":      "До оптимизации",
        "system":     "You are a helpful assistant.",
        "temperature": 0.7,
        "max_tokens":  512,
        "num_ctx":     2048,
    },
    "after": {
        "label":      "После оптимизации",
        "system": (
            "Ты — эксперт по книгам и литературный советник.\n\n"
            "Когда пользователь описывает что хочет почитать, ты рекомендуешь книгу строго в таком формате:\n\n"
            "📖 **Название** (Автор)\n"
            "[2-3 предложения почему именно эта книга подходит под запрос]\n\n"
            "Похожие:\n"
            "• Название (Автор)\n"
            "• Название (Автор)\n"
            "• Название (Автор)\n\n"
            "Правила:\n"
            "— Никогда не повторяй книги, которые уже рекомендовал в этом разговоре\n"
            "— Отвечай на русском"
        ),
        "temperature": 0.8,
        "max_tokens":  400,
        "num_ctx":     8192,
    },
}


def format_score(text: str) -> int:
    """Оценка соответствия формату: 0-3 балла."""
    score = 0
    if "📖" in text or "**" in text:
        score += 1
    if "Похожие" in text or "похожие" in text:
        score += 1
    if text.count("•") >= 3 or text.count("-") >= 3:
        score += 1
    return score


def call(config: dict, query: str) -> dict:
    messages = [
        {"role": "system", "content": config["system"]},
        {"role": "user",   "content": query},
    ]
    body = {
        "model":    MODEL,
        "messages": messages,
        "stream":   False,
        "options": {
            "temperature": config["temperature"],
            "num_predict": config["max_tokens"],
            "num_ctx":     config["num_ctx"],
        },
    }
    t0 = time.time()
    resp = requests.post(URL, json=body, timeout=120)
    resp.raise_for_status()
    elapsed = round(time.time() - t0, 2)
    text = resp.json()["message"]["content"].strip()
    return {
        "query":   query,
        "answer":  text,
        "time":    elapsed,
        "length":  len(text),
        "format":  format_score(text),
    }


def run(config_key: str) -> dict:
    cfg = CONFIGS[config_key]
    print(f"\n  [{cfg['label']}]")
    results = []
    for q in QUERIES:
        print(f"    • {q[:40]}...", end=" ", flush=True)
        r = call(cfg, q)
        results.append(r)
        print(f"{r['time']}s  format={r['format']}/3")

    return {
        "config":    config_key,
        "label":     cfg["label"],
        "params":    {k: v for k, v in cfg.items() if k != "system"},
        "results":   results,
        "avg_time":  round(sum(r["time"]   for r in results) / len(results), 2),
        "avg_len":   int(sum(r["length"] for r in results) / len(results)),
        "avg_fmt":   round(sum(r["format"] for r in results) / len(results), 2),
    }


if __name__ == "__main__":
    print("=" * 55)
    print("  Сравнение: до vs после оптимизации")
    print("=" * 55)

    data = {}
    for key in ("before", "after"):
        data[key] = run(key)

    out = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n  Результаты → {out}")
    print("  Запусти visualize.py для графиков.")
