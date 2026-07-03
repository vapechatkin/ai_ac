"""
Интерактивный поиск по обоим индексам сразу — удобно для live-демо.

Вводишь запрос -> получаешь top-3 из fixed и top-3 из structure бок о бок.
"""

import json
import os

import faiss
import numpy as np
import requests

INDEX_DIR = os.path.join(os.path.dirname(__file__), "data", "index")
OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "nomic-embed-text"
TOP_K = 3


def load_strategy(name: str):
    index = faiss.read_index(os.path.join(INDEX_DIR, f"{name}.faiss"))
    with open(os.path.join(INDEX_DIR, f"{name}_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


def embed_query(text: str) -> np.ndarray:
    resp = requests.post(OLLAMA_URL, json={"model": MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def search(index, meta, query_vec, k=TOP_K):
    scores, ids = index.search(query_vec, k)
    return [(float(s), meta[i]) for s, i in zip(scores[0], ids[0]) if i != -1]


def print_results(label, results):
    print(f"\n  --- {label} ---")
    for score, c in results:
        section = c["section"] or "(нет — fixed не хранит секцию)"
        snippet = c["text"][:160].replace("\n", " ")
        print(f"  score={score:.3f} | {c['source']} | section={section}")
        print(f"    {snippet}...")


def main():
    idx_fixed, meta_fixed = load_strategy("fixed")
    idx_struct, meta_struct = load_strategy("structure")

    print("Интерактивный поиск по индексам fixed / structure.")
    print("Введи вопрос по RAG (или 'exit' для выхода):\n")

    while True:
        try:
            query = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query or query.lower() in ("exit", "quit", "q"):
            break

        qvec = embed_query(query)
        print_results("FIXED", search(idx_fixed, meta_fixed, qvec))
        print_results("STRUCTURE", search(idx_struct, meta_struct, qvec))
        print()


if __name__ == "__main__":
    main()
