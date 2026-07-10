#!/usr/bin/env python3
"""d29: агент-рекомендатор книг на базе локальной LLM (Ollama)."""

import json
import requests

MODEL      = "qwen2.5:3b"
URL        = "http://localhost:11434/api/chat"
TEMP       = 0.8
MAX_TOKENS = 400
NUM_CTX    = 8192

SYSTEM = """Ты — эксперт по книгам и литературный советник.

Когда пользователь описывает что хочет почитать, ты рекомендуешь книгу строго в таком формате:

📖 **Название** (Автор)
[2-3 предложения почему именно эта книга подходит под запрос]

Похожие:
• Название (Автор)
• Название (Автор)
• Название (Автор)

Правила:
— Никогда не повторяй книги, которые уже рекомендовал в этом разговоре
— Если пользователь говорит что книга не подходит или просит другую — рекомендуй новую
— Жанр, язык, эпоха — любые, главное попасть в запрос
— Отвечай на русском"""


def ask(history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM}] + history
    body = {
        "model":   MODEL,
        "messages": messages,
        "stream":  False,
        "options": {
            "temperature": TEMP,
            "num_predict": MAX_TOKENS,
            "num_ctx":     NUM_CTX,
        },
    }
    resp = requests.post(URL, json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def main():
    print("=" * 55)
    print("  📚 Агент-рекомендатор книг (локально, qwen2.5:3b)")
    print("=" * 55)
    print("  Опишите что хотите почитать.")
    print("  'выход' — завершить.\n")

    history = []

    while True:
        try:
            user = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            break

        if not user:
            continue
        if user.lower() in ("выход", "exit", "quit"):
            print("Пока! Приятного чтения 📖")
            break

        history.append({"role": "user", "content": user})

        try:
            reply = ask(history)
        except Exception as e:
            print(f"Ошибка: {e}")
            history.pop()
            continue

        history.append({"role": "assistant", "content": reply})
        print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
