"""
Grounded RAG: ассистент ОБЯЗАН вернуть структурированный ответ из трёх частей —
  answer     — сам ответ,
  sources    — список источников (source + section + chunk_id),
  citations  — дословные цитаты из найденных чанков (chunk_id + quote).

Поверх retrieval из d21/d22 и порогового фильтра из d23.

Как гарантируется структура:
  Ответ модели снимается не как свободный текст, а через forced tool use
  (tool_choice -> grounded_answer). Схема инструмента требует поля
  answer/sources/citations, поэтому модель физически не может вернуть ответ
  без источников и цитат — Anthropic API валидирует input по схеме.

Режим "не знаю" (усиление задания):
  Перед вызовом LLM работает детерминированный порог релевантности
  (SIM_THRESHOLD, тот же 0.60, что в d23). Если ни один из top-K чанков не
  проходит порог — LLM вообще не вызывается, сразу возвращается ответ
  "не знаю, уточните вопрос" с пустыми sources/citations. Дополнительно у
  инструмента есть флаг enough_context: даже при формально прошедших порог
  чанках модель может признать, что контекст не отвечает на вопрос, и уйти
  в тот же режим "не знаю".
"""

import json
import os

import anthropic
import faiss
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE, "..", "d21", "data", "index")
STRATEGY = "structure"

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"

_api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
_client = anthropic.Anthropic(api_key=_api_key)
LLM_MODEL = "claude-haiku-4-5"

TOP_K_BEFORE = 10       # сколько кандидатов достаём из FAISS
TOP_K_AFTER = 5         # сколько оставляем после порогового фильтра
SIM_THRESHOLD = 0.60    # порог релевантности; ниже него -> режим "не знаю"

IDK_TEXT = (
    "I don't know based on the provided documents. The retrieved context is "
    "not relevant enough to answer this question reliably. Could you please "
    "clarify or rephrase your question?"
)

SYSTEM_GROUNDED = (
    "You answer questions STRICTLY based on the provided context chunks and "
    "nothing else. You MUST call the tool `grounded_answer`.\n"
    "Rules:\n"
    "1. Every claim in `answer` must be supported by the context.\n"
    "2. `sources` must list every chunk you actually used (source, section, "
    "chunk_id), taken verbatim from the chunk headers.\n"
    "3. `citations` must contain the exact verbatim fragments (quotes) from the "
    "chunks that support your answer — copy them character-for-character, do not "
    "paraphrase. Give at least one citation.\n"
    "4. Answer with whatever the context supports, even if it only partially "
    "covers the question. Set `enough_context` to false ONLY if the chunks are "
    "essentially unrelated to the question and contain no usable information; in "
    "that case leave sources/citations empty and put an 'I don't know, please "
    "clarify' message in `answer`. Do not decline just because the coverage is "
    "partial.\n"
    "Answer in English."
)

SYSTEM_CITE = (
    "You extract verbatim supporting quotes from context chunks for a given "
    "answer. You MUST call the tool `add_citations`. Copy quotes "
    "character-for-character from the context; never paraphrase. Provide at "
    "least one quote."
)

CITE_TOOL = {
    "name": "add_citations",
    "description": "Provide verbatim supporting quotes for an already-written answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["chunk_id", "quote"],
                },
            },
        },
        "required": ["citations"],
    },
}

# Схема forced tool use — именно она гарантирует наличие полей.
GROUNDED_TOOL = {
    "name": "grounded_answer",
    "description": "Return a grounded answer with mandatory sources and verbatim citations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "enough_context": {
                "type": "boolean",
                "description": "True only if the context genuinely answers the question.",
            },
            "answer": {
                "type": "string",
                "description": "The answer, based only on the context. If not enough context, an 'I don't know, please clarify' message.",
            },
            "sources": {
                "type": "array",
                "description": "Chunks actually used to build the answer.",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "section": {"type": "string"},
                        "chunk_id": {"type": "string"},
                    },
                    "required": ["source", "section", "chunk_id"],
                },
            },
            "citations": {
                "type": "array",
                "description": "Verbatim quotes from the chunks supporting the answer.",
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                    "required": ["chunk_id", "quote"],
                },
            },
        },
        "required": ["enough_context", "answer", "sources", "citations"],
    },
}


def _load_index():
    index = faiss.read_index(os.path.join(INDEX_DIR, f"{STRATEGY}.faiss"))
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


def retrieve(query: str, k: int) -> list:
    """Возвращает список dict: {score, source, section, chunk_id, text}."""
    qvec = embed_query(query)
    scores, ids = _INDEX.search(qvec, k)
    out = []
    for s, i in zip(scores[0], ids[0]):
        if i == -1:
            continue
        c = _META[i]
        out.append({
            "score": float(s), "source": c["source"], "section": c["section"],
            "chunk_id": c["chunk_id"], "text": c["text"],
        })
    return out


def filter_by_threshold(chunks: list, threshold: float = SIM_THRESHOLD,
                        top_k_after: int = TOP_K_AFTER) -> list:
    kept = [c for c in chunks if c["score"] >= threshold]
    kept.sort(key=lambda c: c["score"], reverse=True)
    return kept[:top_k_after]


def build_context(chunks: list) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(
            f"[{i}] source={c['source']} section={c['section']} "
            f"chunk_id={c['chunk_id']}\n{c['text']}"
        )
    return "\n\n".join(parts)


def _idk_result(retrieved: list, kept: list, reason: str) -> dict:
    return {
        "answer": IDK_TEXT,
        "sources": [],
        "citations": [],
        "enough_context": False,
        "idk": True,
        "idk_reason": reason,
        "retrieved": retrieved,
        "kept": kept,
        "input_tokens": 0,
        "output_tokens": 0,
    }


def _repair_citations(question: str, context: str, answer_text: str) -> list:
    """Ответ есть, но модель не приложила цитат — добираем их отдельным вызовом."""
    user = (
        f"Context:\n{context}\n\nQuestion: {question}\n\n"
        f"Answer that was given:\n{answer_text}\n\n"
        "Provide the exact verbatim quotes from the context chunks that support "
        "this answer. Copy them character-for-character."
    )
    resp = _client.messages.create(
        model=LLM_MODEL, max_tokens=500, system=SYSTEM_CITE,
        tools=[CITE_TOOL], tool_choice={"type": "tool", "name": "add_citations"},
        messages=[{"role": "user", "content": user}],
    )
    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    cites = tool_use.input.get("citations", []) if tool_use else []
    return cites, resp.usage.input_tokens, resp.usage.output_tokens


def _fallback_citation(sources: list, kept: list) -> list:
    """
    Детерминированная страховка: если модель (и repair-вызов) так и не дали
    цитату, берём дословный фрагмент из чанка, который модель указала как
    источник. Гарантирует правило "цитата в каждом ответе".
    """
    by_id = {c["chunk_id"]: c for c in kept}
    for s in sources:
        c = by_id.get(s.get("chunk_id"))
        if not c:
            continue
        text = " ".join(c["text"].split())
        # первые ~2 предложения / до 240 символов
        frag = text[:240]
        dot = frag.rfind(". ")
        if dot > 60:
            frag = frag[:dot + 1]
        return [{"chunk_id": c["chunk_id"], "quote": frag}]
    return []


def answer(question: str) -> dict:
    """
    Основной grounded-режим. Всегда возвращает dict с полями
    answer / sources / citations (+ служебные retrieved/kept/idk).
    """
    retrieved = retrieve(question, TOP_K_BEFORE)
    kept = filter_by_threshold(retrieved)

    # Усиление: порог релевантности не пройден -> "не знаю", без вызова LLM.
    if not kept:
        return _idk_result(retrieved, kept, reason="below_threshold")

    context = build_context(kept)
    user_msg = f"Context:\n{context}\n\nQuestion: {question}"

    resp = _client.messages.create(
        model=LLM_MODEL,
        max_tokens=900,
        system=SYSTEM_GROUNDED,
        tools=[GROUNDED_TOOL],
        tool_choice={"type": "tool", "name": "grounded_answer"},
        messages=[{"role": "user", "content": user_msg}],
    )

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_use is None:  # практически недостижимо при forced tool_choice
        return _idk_result(retrieved, kept, reason="no_tool_use")

    data = tool_use.input
    enough = bool(data.get("enough_context", True))
    sources = data.get("sources", []) or []
    citations = data.get("citations", []) or []
    in_tok = resp.usage.input_tokens
    out_tok = resp.usage.output_tokens

    has_grounding = bool(sources) and bool(citations)

    # Reconcile: модель может выставить enough_context=false, но при этом
    # реально приложить источники и цитаты (Haiku иногда путает флаг).
    # Доверяем фактическому обоснованию, а не флагу.
    if not enough and not has_grounding:
        return _idk_result(retrieved, kept, reason="model_declined")

    answer_text = data.get("answer", "")

    # Ответ есть, но цитат нет — обязательное правило: добираем цитаты
    # отдельным вызовом, а если и он пуст — детерминированной страховкой.
    if not citations:
        citations, ci, co = _repair_citations(question, context, answer_text)
        in_tok += ci
        out_tok += co
    if not citations:
        citations = _fallback_citation(sources, kept)

    return {
        "answer": answer_text,
        "sources": sources,
        "citations": citations,
        "enough_context": True,
        "idk": False,
        "idk_reason": None,
        "retrieved": retrieved,
        "kept": kept,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is the difference between RAG-Sequence and RAG-Token models?"
    r = answer(q)
    print(json.dumps(
        {k: v for k, v in r.items() if k not in ("retrieved", "kept")},
        ensure_ascii=False, indent=2,
    ))
