"""
d28: сравнение локальной (qwen2.5:3b) и облачной (claude-haiku) RAG.
"""

import json
import os

from rag_local import LOCAL_MODEL, ANTHROPIC_MODEL, ask

QUESTIONS = [
    "What is the difference between RAG-Sequence and RAG-Token models?",
    "What are the three RAG paradigms described in the RAG survey?",
    "What chunking strategies are commonly used in RAG pipelines?",
    "What is the role of the retriever in a RAG system?",
    "How does reranking improve RAG quality?",
]

if __name__ == "__main__":
    results = []
    for q in QUESTIONS:
        print(f"Q: {q}")
        res = ask(q, compare=True)
        results.append(res)
        print(f"  chunks : {len(res['chunks'])}")
        print(f"  local  ({res['local_time']}s): {res['answer_local'][:120]}...")
        if "answer_cloud" in res:
            print(f"  cloud  ({res['cloud_time']}s): {res['answer_cloud'][:120]}...")
        print()

    out = os.path.join(os.path.dirname(__file__), "results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Результаты → {out}")
    print(f"\n{'Вопрос':<50} {'Local':>7} {'Cloud':>7}")
    print("-" * 66)
    for r in results:
        q = r["question"][:49]
        lt = f"{r['local_time']}s"
        ct = f"{r.get('cloud_time', '—')}s"
        print(f"{q:<50} {lt:>7} {ct:>7}")

    avg_local = sum(r["local_time"] for r in results) / len(results)
    avg_cloud = sum(r.get("cloud_time", 0) for r in results) / len(results)
    print(f"\nСреднее время: local={avg_local:.1f}s  cloud={avg_cloud:.1f}s")
