"""
Строит FAISS-индекс (cosine similarity через нормализованные векторы + IndexFlatIP)
для каждой стратегии chunking и сохраняет его вместе с метаданными чанков.

Вход:  data/chunks/{fixed,structure}.json, data/embeddings/{fixed,structure}.npy
Выход: data/index/{fixed,structure}.faiss
       data/index/{fixed,structure}_meta.json  (метаданные чанков в порядке индекса)
"""

import json
import os

import faiss
import numpy as np

CHUNKS_DIR = os.path.join(os.path.dirname(__file__), "data", "chunks")
EMB_DIR = os.path.join(os.path.dirname(__file__), "data", "embeddings")
INDEX_DIR = os.path.join(os.path.dirname(__file__), "data", "index")


def build(strategy: str):
    with open(os.path.join(CHUNKS_DIR, f"{strategy}.json"), encoding="utf-8") as f:
        chunks = json.load(f)
    vectors = np.load(os.path.join(EMB_DIR, f"{strategy}.npy")).astype("float32")

    faiss.normalize_L2(vectors)  # для косинусного сходства через inner product
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, os.path.join(INDEX_DIR, f"{strategy}.faiss"))
    with open(os.path.join(INDEX_DIR, f"{strategy}_meta.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"{strategy}: индекс из {index.ntotal} векторов размерности {vectors.shape[1]} сохранён")


def main():
    for strategy in ("fixed", "structure"):
        build(strategy)


if __name__ == "__main__":
    main()
