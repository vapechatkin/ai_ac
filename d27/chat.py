#!/usr/bin/env python3
"""d27: CLI-чат с локальной LLM через Ollama."""

import json
import sys
import urllib.request

MODEL = "qwen2.5:0.5b"
URL   = "http://localhost:11434/api/chat"


def ask(history: list) -> str:
    body = json.dumps({"model": MODEL, "messages": history, "stream": False}).encode()
    req  = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["message"]["content"].strip()


def main():
    print(f"Чат с {MODEL}  (ollama локально)")
    print("Введите сообщение. Ctrl+C или 'выход' для выхода.\n")

    history = []
    while True:
        try:
            user_input = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("выход", "exit", "quit"):
            print("Пока!")
            break

        history.append({"role": "user", "content": user_input})

        try:
            reply = ask(history)
        except Exception as e:
            print(f"Ошибка: {e}")
            history.pop()
            continue

        history.append({"role": "assistant", "content": reply})
        print(f"\nАссистент: {reply}\n")


if __name__ == "__main__":
    main()
