"""
d28: RAG полностью локально через Ollama.
Retrieval — FAISS-индекс из d21 + nomic-embed-text.
Генерация — qwen2.5:3b (локально).
Сравнение с Anthropic claude-haiku-4-5.
"""

import json
import os
import time

import anthropic
import faiss
import numpy as np
import requests
from dotenv import load_dotenv

BASE      = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE, "..", "d24", ".env"), override=False)
load_dotenv(override=False)
INDEX_DIR = os.path.join(BASE, "..", "d21", "data", "index")
STRATEGY  = "structure"

OLLAMA_BASE  = "http://localhost:11434"
EMBED_MODEL  = "nomic-embed-text"
LOCAL_MODEL  = "qwen2.5:3b"

ANTHROPIC_MODEL = "claude-haiku-4-5"
_anthro = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))

TOP_K         = 5
SIM_THRESHOLD = 0.45

# ── Загрузка индекса ────────────────────────────────────────────────────────
_index = faiss.read_index(os.path.join(INDEX_DIR, f"{STRATEGY}.faiss"))
with open(os.path.join(INDEX_DIR, f"{STRATEGY}_meta.json"), encoding="utf-8") as f:
    _meta = json.load(f)


# ── Retrieval ────────────────────────────────────────────────────────────────
def embed(text: str) -> np.ndarray:
    resp = requests.post(f"{OLLAMA_BASE}/api/embed",
                         json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(query: str) -> list:
    qvec = embed(query)
    scores, ids = _index.search(qvec, TOP_K * 2)
    chunks = []
    for s, i in zip(scores[0], ids[0]):
        if i == -1 or s < SIM_THRESHOLD:
            continue
        c = _meta[i]
        chunks.append({"score": float(s), "source": c["source"],
                        "section": c["section"], "text": c["text"]})
    chunks.sort(key=lambda x: x["score"], reverse=True)
    return chunks[:TOP_K]


def build_context(chunks: list) -> str:
    return "\n\n".join(
        f"[{i+1}] {c['source']} / {c['section']}\n{c['text']}"
        for i, c in enumerate(chunks)
    )


# ── Генерация: Ollama ────────────────────────────────────────────────────────
def generate_local(question: str, context: str) -> tuple[str, float]:
    messages = [
        {"role": "system", "content":
            "Ты помощник. Отвечай ТОЛЬКО на основе предоставленного контекста. "
            "Если контекст не содержит ответа — скажи 'не знаю'."},
        {"role": "user", "content": f"Контекст:\n{context}\n\nВопрос: {question}"},
    ]
    t0 = time.time()
    resp = requests.post(f"{OLLAMA_BASE}/api/chat",
                         json={"model": LOCAL_MODEL, "messages": messages, "stream": False},
                         timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"].strip(), time.time() - t0


# ── Генерация: Anthropic ─────────────────────────────────────────────────────
def generate_cloud(question: str, context: str) -> tuple[str, float]:
    t0 = time.time()
    resp = _anthro.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=600,
        system=("Answer ONLY based on the provided context. "
                "If the context doesn't contain the answer, say 'I don't know'."),
        messages=[{"role": "user",
                   "content": f"Context:\n{context}\n\nQuestion: {question}"}],
    )
    return resp.content[0].text.strip(), time.time() - t0


# ── Основная функция ─────────────────────────────────────────────────────────
def ask(question: str, compare: bool = False) -> dict:
    chunks = retrieve(question)
    if not chunks:
        return {"question": question, "answer_local": "не знаю (нет релевантных чанков)",
                "chunks": [], "local_time": 0}

    context = build_context(chunks)
    answer_local, local_time = generate_local(question, context)

    result = {
        "question":     question,
        "chunks_found": len(chunks),
        "answer_local": answer_local,
        "local_time":   round(local_time, 2),
        "chunks":       chunks,
    }

    if compare:
        answer_cloud, cloud_time = generate_cloud(question, context)
        result["answer_cloud"] = answer_cloud
        result["cloud_time"]   = round(cloud_time, 2)

    return result


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Local RAG с Ollama")
    parser.add_argument("--compare", action="store_true",
                        help="Сравнить с Anthropic claude-haiku")
    args = parser.parse_args()

    print(f"RAG локально ({LOCAL_MODEL}) {'+ Anthropic' if args.compare else ''}")
    print("Введите вопрос. Ctrl+C или 'выход' для выхода.\n")

    while True:
        try:
            q = input("Вопрос: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            break
        if not q or q.lower() in ("выход", "exit", "quit"):
            break

        res = ask(q, compare=args.compare)
        print(f"\nНайдено чанков: {res['chunks_found']}")
        print(f"\n[Локально {LOCAL_MODEL}] ({res['local_time']}s):\n{res['answer_local']}")
        if args.compare and "answer_cloud" in res:
            print(f"\n[Облако {ANTHROPIC_MODEL}] ({res['cloud_time']}s):\n{res['answer_cloud']}")
        print()
