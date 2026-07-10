#!/usr/bin/env python3
"""d29: агент-рекомендатор книг с RAG — только реальные книги из базы."""

import json
import os

import faiss
import numpy as np
import requests

BASE       = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE, "data", "books.faiss")
META_FILE  = os.path.join(BASE, "data", "books_meta.json")

OLLAMA_URL  = "http://localhost:11434/api/chat"
EMBED_URL   = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL  = "qwen2.5:3b"
TOP_K       = 6

SYSTEM = """Ты — литературный советник. Тебе передан список реальных книг из базы данных.
Твоя задача — выбрать ОДНУ лучшую книгу из предложенных и порекомендовать её.

Отвечай строго в этом формате:

📖 **Название** (Автор, год)
[2-3 предложения почему именно эта книга подходит под запрос пользователя]

Похожие из базы:
• Название (Автор)
• Название (Автор)
• Название (Автор)

ВАЖНО: используй ТОЛЬКО книги из предоставленного списка. Не выдумывай книги."""

# Загрузка индекса
if not os.path.exists(INDEX_FILE):
    print("Индекс не найден. Запусти: python3 build_index.py")
    exit(1)

_index = faiss.read_index(INDEX_FILE)
with open(META_FILE, encoding="utf-8") as f:
    _meta = json.load(f)


def embed_query(text: str) -> np.ndarray:
    resp = requests.post(EMBED_URL, json={"model": EMBED_MODEL, "input": [text]}, timeout=30)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(query: str) -> list:
    vec = embed_query(query)
    scores, ids = _index.search(vec, TOP_K)
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        book = _meta[idx]
        results.append({**book, "score": float(score)})
    return results


def build_context(books: list) -> str:
    lines = []
    for b in books:
        lines.append(
            f"- **{b['title']}** ({b['author']}, {b['year']}) "
            f"[{', '.join(b['genre'])}]\n  {b['description']}"
        )
    return "\n".join(lines)


def chat(history: list) -> str:
    messages = [{"role": "system", "content": SYSTEM}] + history
    resp = requests.post(OLLAMA_URL, json={
        "model":   CHAT_MODEL,
        "messages": messages,
        "stream":  False,
        "options": {"temperature": 0.5, "num_predict": 400, "num_ctx": 8192},
    }, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip()


def main():
    print("=" * 57)
    print("  📚 Рекомендатор книг с RAG (100 реальных книг)")
    print("=" * 57)
    print("  Опишите что хотите почитать.")
    print("  'выход' — завершить.\n")

    history = []

    while True:
        try:
            user = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            break

        if not user or user.lower() in ("выход", "exit", "quit"):
            print("Приятного чтения 📖")
            break

        # Retrieval
        books = retrieve(user)
        context = build_context(books)

        # Формируем сообщение с контекстом
        msg = f"Запрос пользователя: {user}\n\nДоступные книги из базы:\n{context}"
        history.append({"role": "user", "content": msg})

        reply = chat(history)
        history.append({"role": "assistant", "content": reply})

        print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
