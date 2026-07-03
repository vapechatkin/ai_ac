"""
Ядро агента с двумя режимами: без RAG и с RAG.

RAG-режим: вопрос -> эмбеддинг вопроса (Ollama) -> поиск top-k чанков в
FAISS-индексе из d21 (structure-стратегия) -> контекст + вопрос -> Claude API.
No-RAG режим: вопрос напрямую в Claude API, без внешнего контекста.

Индекс переиспользуется из ../d21/data/index (собран в предыдущем задании),
здесь заново ничего не индексируется.
"""

import os

import anthropic
import faiss
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE, "..", "d21", "data", "index")
STRATEGY = "structure"  # в d21 показала лучшее качество поиска, чем fixed

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
_client = anthropic.Anthropic(api_key=_api_key)
LLM_MODEL = "claude-haiku-4-5"

TOP_K = 5

SYSTEM_NO_RAG = (
    "Ты полезный ассистент. Отвечай кратко и по делу, основываясь только на "
    "своих собственных знаниях. Отвечай на английском языке."
)

SYSTEM_RAG = (
    "Ты отвечаешь на вопросы ТОЛЬКО на основе предоставленных фрагментов "
    "документов (контекста). Если ответа нет в контексте — прямо скажи, что "
    "в предоставленных материалах этого нет, не выдумывай. "
    "В конце ответа укажи использованные источники в формате "
    "[source, section]. Отвечай на английском языке."
)


def _load_index():
    index = faiss.read_index(os.path.join(INDEX_DIR, f"{STRATEGY}.faiss"))
    import json
    with open(os.path.join(INDEX_DIR, f"{STRATEGY}_meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


_INDEX, _META = _load_index()


def embed_query(text: str) -> np.ndarray:
    resp = requests.post(OLLAMA_URL, json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(question: str, k: int = TOP_K) -> list:
    qvec = embed_query(question)
    scores, ids = _INDEX.search(qvec, k)
    return [(float(s), _META[i]) for s, i in zip(scores[0], ids[0]) if i != -1]


def build_context(chunks: list) -> str:
    parts = []
    for i, (score, c) in enumerate(chunks, start=1):
        parts.append(
            f"[{i}] source={c['source']} section={c['section']}\n{c['text']}"
        )
    return "\n\n".join(parts)


def call_llm(system: str, user: str) -> dict:
    resp = _client.messages.create(
        model=LLM_MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return {
        "text": resp.content[0].text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


def answer_no_rag(question: str) -> dict:
    result = call_llm(SYSTEM_NO_RAG, question)
    result["mode"] = "no_rag"
    result["retrieved"] = []
    return result


def answer_rag(question: str, k: int = TOP_K) -> dict:
    chunks = retrieve(question, k)
    context = build_context(chunks)
    user_msg = f"Контекст:\n{context}\n\nВопрос: {question}"
    result = call_llm(SYSTEM_RAG, user_msg)
    result["mode"] = "rag"
    result["retrieved"] = [
        {"score": score, "source": c["source"], "section": c["section"], "chunk_id": c["chunk_id"]}
        for score, c in chunks
    ]
    return result


def answer(question: str, mode: str, k: int = TOP_K) -> dict:
    if mode == "rag":
        return answer_rag(question, k)
    if mode == "no_rag":
        return answer_no_rag(question)
    raise ValueError(f"Неизвестный режим: {mode}")
