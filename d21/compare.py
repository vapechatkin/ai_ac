"""
Сравнение двух стратегий chunking (fixed vs structure):
  1. Количественная статистика по чанкам (размер, разброс, число на документ).
  2. Качественное сравнение поиска: одни и те же запросы гоняются по обоим
     FAISS-индексам, сравниваются top-k результаты.

Результат печатается в консоль и сохраняется в data/comparison_report.md
"""

import json
import os
import statistics

import faiss
import numpy as np
import requests

INDEX_DIR = os.path.join(os.path.dirname(__file__), "data", "index")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "data", "comparison_report.md")

OLLAMA_URL = "http://localhost:11434/api/embed"
MODEL = "nomic-embed-text"

TEST_QUERIES = [
    "What is the difference between RAG-Sequence and RAG-Token models?",
    "How does the retriever component work in RAG?",
    "What are the main challenges and limitations of naive RAG?",
    "How is chunking used in the indexing pipeline of RAG systems?",
    "What evaluation metrics are used to assess RAG systems?",
]

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
    results = []
    for score, idx in zip(scores[0], ids[0]):
        if idx == -1:
            continue
        chunk = meta[idx]
        results.append((float(score), chunk))
    return results


def size_stats(meta):
    sizes = [c["char_count"] for c in meta]
    by_doc = {}
    for c in meta:
        by_doc.setdefault(c["source"], 0)
        by_doc[c["source"]] += 1
    return {
        "n_chunks": len(meta),
        "avg": statistics.mean(sizes),
        "stdev": statistics.stdev(sizes) if len(sizes) > 1 else 0,
        "min": min(sizes),
        "max": max(sizes),
        "by_doc": by_doc,
    }


def main():
    idx_fixed, meta_fixed = load_strategy("fixed")
    idx_struct, meta_struct = load_strategy("structure")

    lines = ["# Сравнение стратегий chunking: fixed vs structure\n"]

    # --- количественная статистика ---
    lines.append("## 1. Статистика по чанкам\n")
    for name, meta in (("fixed", meta_fixed), ("structure", meta_struct)):
        s = size_stats(meta)
        lines.append(f"**{name}**: {s['n_chunks']} чанков, "
                      f"средний размер {s['avg']:.0f} симв. (σ={s['stdev']:.0f}), "
                      f"min={s['min']}, max={s['max']}")
        lines.append(f"  чанков на документ: {s['by_doc']}\n")

    print("\n".join(lines))

    # --- качественное сравнение поиска ---
    lines.append("## 2. Сравнение поиска по тестовым запросам (top-3)\n")
    for query in TEST_QUERIES:
        qvec = embed_query(query)
        res_fixed = search(idx_fixed, meta_fixed, qvec)
        res_struct = search(idx_struct, meta_struct, qvec)

        lines.append(f"### Запрос: {query}\n")
        print(f"\n### Запрос: {query}")

        for label, results in (("FIXED", res_fixed), ("STRUCTURE", res_struct)):
            lines.append(f"**{label}:**\n")
            print(f"  [{label}]")
            for score, c in results:
                section = c["section"] or "-"
                snippet = c["text"][:140].replace("\n", " ")
                line = (f"- score={score:.3f} | {c['source']} | section=\"{section}\" | "
                        f"{snippet}...")
                lines.append(line)
                print(f"    {line}")
            lines.append("")

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\nОтчёт сохранён в {REPORT_PATH}")


if __name__ == "__main__":
    main()
