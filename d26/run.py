#!/usr/bin/env python3
"""d26: локальная LLM через Ollama — 3 запроса разной сложности."""

import json
import time
import urllib.request

MODEL = "qwen2.5:0.5b"
BASE_URL = "http://localhost:11434"


def check_server():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models", [])]
        print(f"✅ Ollama запущена. Модели: {models}\n")
        return True
    except Exception as e:
        print(f"❌ Сервер недоступен: {e}")
        return False


def chat(prompt: str, system: str = "") -> tuple[str, float]:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = json.dumps({"model": MODEL, "messages": messages, "stream": False}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    elapsed = time.time() - t0
    return data["message"]["content"].strip(), elapsed


def run_query(n: int, label: str, prompt: str, system: str = ""):
    print(f"{'='*60}")
    print(f"Запрос #{n} [{label}]")
    print(f"Промпт: {prompt}")
    if system:
        print(f"System: {system}")
    print("-" * 60)
    answer, elapsed = chat(prompt, system)
    print(f"Ответ: {answer}")
    print(f"⏱  {elapsed:.1f}s")
    print()


def main():
    print("🦙 d26 — локальная LLM (Ollama + qwen2.5:0.5b)\n")

    if not check_server():
        return

    # 1. Простой: факт
    run_query(
        1,
        "простой",
        "Что такое Ollama? Ответь одним предложением.",
    )

    # 2. Средний: рассуждение
    run_query(
        2,
        "средний",
        "Перечисли 3 преимущества запуска LLM локально по сравнению с облаком.",
    )

    # 3. Сложный: код
    run_query(
        3,
        "сложный — генерация кода",
        "Напиши функцию на Python, которая проверяет, является ли число простым.",
        system="Ты — опытный Python-разработчик. Давай только код без лишних объяснений.",
    )

    print("✅ Все запросы выполнены.")


if __name__ == "__main__":
    main()
