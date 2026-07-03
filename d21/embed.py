"""
Генерация эмбеддингов для чанков через локальный Ollama (nomic-embed-text).

Читает data/chunks/{fixed,structure}.json, для каждого чанка получает
эмбеддинг батчами через Ollama HTTP API и сохраняет вектора в .npy рядом
с чанками (data/embeddings/{fixed,structure}.npy), сохраняя порядок.
"""

import json
import os
import sys
import time

import numpy as np
import requests

CHUNKS_DIR = os.path.join(os.path.dirname(__file__), "data", "chunks")
EMB_DIR = os.path.join(os.path.dirname(__file__), "data", "embeddings")

OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "nomic-embed-text"
BATCH_SIZE = 16


def embed_batch(texts: list) -> list:
    resp = requests.post(OLLAMA_URL, json={"model": MODEL, "input": texts}, timeout=120)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def embed_chunks(chunks: list, label: str) -> np.ndarray:
    vectors = []
    t0 = time.time()
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i + BATCH_SIZE]
        texts = [c["text"] for c in batch]
        vecs = embed_batch(texts)
        vectors.extend(vecs)
        print(f"  [{label}] {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)}", end="\r")
    print(f"  [{label}] {len(chunks)}/{len(chunks)} готово за {time.time() - t0:.1f}с")
    return np.array(vectors, dtype="float32")


def main():
    os.makedirs(EMB_DIR, exist_ok=True)
    for strategy in ("fixed", "structure"):
        chunk_path = os.path.join(CHUNKS_DIR, f"{strategy}.json")
        if not os.path.exists(chunk_path):
            print(f"Нет {chunk_path}, запусти chunking.py")
            sys.exit(1)
        with open(chunk_path, encoding="utf-8") as f:
            chunks = json.load(f)

        vectors = embed_chunks(chunks, strategy)
        out_path = os.path.join(EMB_DIR, f"{strategy}.npy")
        np.save(out_path, vectors)
        print(f"{strategy}: {vectors.shape} -> {out_path}")


if __name__ == "__main__":
    main()
