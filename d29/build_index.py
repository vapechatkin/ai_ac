"""d29: строит FAISS-индекс по базе книг через nomic-embed-text (Ollama)."""

import json
import os

import faiss
import numpy as np
import requests

BASE      = os.path.dirname(os.path.abspath(__file__))
BOOKS_FILE = os.path.join(BASE, "data", "books.json")
INDEX_FILE = os.path.join(BASE, "data", "books.faiss")
META_FILE  = os.path.join(BASE, "data", "books_meta.json")

EMBED_MODEL = "nomic-embed-text"
OLLAMA_URL  = "http://localhost:11434/api/embed"


def embed(texts: list[str]) -> np.ndarray:
    resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": texts}, timeout=60)
    resp.raise_for_status()
    return np.array(resp.json()["embeddings"], dtype="float32")


def book_text(b: dict) -> str:
    return (
        f"{b['title']} — {b['author']}. "
        f"Жанр: {', '.join(b['genre'])}. "
        f"Теги: {', '.join(b['tags'])}. "
        f"{b['description']}"
    )


if __name__ == "__main__":
    with open(BOOKS_FILE, encoding="utf-8") as f:
        books = json.load(f)

    print(f"Индексируем {len(books)} книг...")

    texts = [book_text(b) for b in books]

    # Эмбеддим батчами по 20
    all_vecs = []
    batch = 20
    for i in range(0, len(texts), batch):
        chunk = texts[i:i+batch]
        vecs = embed(chunk)
        all_vecs.append(vecs)
        print(f"  {min(i+batch, len(texts))}/{len(texts)}")

    matrix = np.vstack(all_vecs)
    faiss.normalize_L2(matrix)

    index = faiss.IndexFlatIP(matrix.shape[1])
    index.add(matrix)
    faiss.write_index(index, INDEX_FILE)

    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)

    print(f"Готово: {INDEX_FILE}  ({len(books)} векторов, dim={matrix.shape[1]})")
