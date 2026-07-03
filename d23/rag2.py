"""
Улучшенный RAG: второй этап после поиска (фильтр релевантности / реранкер)
+ query rewriting, поверх индекса и retrieval-логики из d21/d22.

Эмпирика (см. README): на нашем корпусе (3 статьи про RAG, одна тема)
релевантные вопросы дают top-10 similarity в диапазоне ~0.66-0.87,
а вопросы не по теме корпуса — ~0.37-0.57. Порог 0.60 отделяет
"вопрос вообще не по корпусу" от "вопрос по теме", поэтому используется
как abs threshold; сам topK-cutoff (10 -> 5) — это дополнительное
сужение до самых сильных совпадений.

Режимы (answer(question, mode)):
  no_rag         — без RAG (как в d22)
  baseline       — RAG без фильтра: top-5 сразу в контекст (как в d22)
  threshold      — top-10 -> порог similarity 0.60 -> top-5
  llm_rerank     — top-10 -> Claude оценивает релевантность каждого чанка
                   0-10 одним batched-вызовом -> порог >=6 -> top-5
  rewrite_filter — Claude переформулирует вопрос в поисковый запрос ->
                   top-10 по переформулированному запросу -> threshold -> top-5
"""

import json
import os
import re

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

TOP_K_BEFORE = 10     # сколько кандидатов достаём из FAISS до фильтрации
TOP_K_AFTER = 5        # сколько оставляем после фильтрации/реранкинга
SIM_THRESHOLD = 0.60    # порог отсечения по косинусному сходству
RERANK_MIN_SCORE = 6    # порог отсечения по LLM-реранкеру (шкала 0-10)

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

SYSTEM_REWRITE = (
    "Ты переформулируешь пользовательский вопрос в оптимальный поисковый "
    "запрос для семантического поиска (embedding search) по корпусу "
    "академических статей о Retrieval-Augmented Generation (RAG). "
    "Убери разговорные обороты, оставь ключевые термины и понятия. "
    "Ответь ТОЛЬКО переформулированным запросом, без пояснений, на английском."
)

SYSTEM_RERANK = (
    "Ты оцениваешь релевантность фрагментов текста вопросу пользователя. "
    "Для каждого фрагмента дай оценку релевантности от 0 (совсем не по теме) "
    "до 10 (прямо отвечает на вопрос). "
    "Ответь СТРОГО в формате JSON-массива чисел, без пояснений, например: "
    "[8, 3, 0, 6, 9]. Длина массива должна совпадать с числом фрагментов."
)


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


def call_llm(system: str, user: str, max_tokens: int = 600) -> dict:
    resp = _client.messages.create(
        model=LLM_MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    return {
        "text": resp.content[0].text,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


# --------------------------------------------------------------- этап 2: фильтр/реранк

def filter_by_threshold(chunks: list, threshold: float = SIM_THRESHOLD,
                         top_k_after: int = TOP_K_AFTER) -> list:
    kept = [c for c in chunks if c["score"] >= threshold]
    kept.sort(key=lambda c: c["score"], reverse=True)
    return kept[:top_k_after]


def llm_rerank(question: str, chunks: list, top_k_after: int = TOP_K_AFTER,
               min_score: int = RERANK_MIN_SCORE) -> list:
    if not chunks:
        return []
    listing = "\n\n".join(
        f"[{i}] {c['text'][:500]}" for i, c in enumerate(chunks)
    )
    user = f"Вопрос: {question}\n\nФрагменты:\n{listing}"
    result = call_llm(SYSTEM_RERANK, user, max_tokens=200)
    match = re.search(r"\[[\d,\s]+\]", result["text"])
    if not match:
        # реранкер не распарсился — не режем, просто берём top_k_after по исходному score
        ranked = sorted(chunks, key=lambda c: c["score"], reverse=True)
        return ranked[:top_k_after]

    scores = json.loads(match.group(0))
    for c, s in zip(chunks, scores):
        c["rerank_score"] = s
    kept = [c for c in chunks if c.get("rerank_score", 0) >= min_score]
    kept.sort(key=lambda c: c["rerank_score"], reverse=True)
    return kept[:top_k_after]


def rewrite_query(question: str) -> str:
    result = call_llm(SYSTEM_REWRITE, question, max_tokens=100)
    return result["text"].strip().strip('"')


# --------------------------------------------------------------- сборка контекста + ответ

def build_context(chunks: list) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[{i}] source={c['source']} section={c['section']}\n{c['text']}")
    return "\n\n".join(parts)


def _answer_with_chunks(question: str, retrieved: list, kept: list) -> dict:
    if not kept:
        return {
            "text": "Ни один из найденных фрагментов не прошёл фильтр релевантности — "
                    "в базе, вероятно, нет ответа на этот вопрос.",
            "input_tokens": 0, "output_tokens": 0,
            "retrieved": retrieved, "kept": kept,
        }
    context = build_context(kept)
    user_msg = f"Контекст:\n{context}\n\nВопрос: {question}"
    result = call_llm(SYSTEM_RAG, user_msg)
    result["retrieved"] = retrieved
    result["kept"] = kept
    return result


def answer_no_rag(question: str) -> dict:
    result = call_llm(SYSTEM_NO_RAG, question)
    result["retrieved"] = []
    result["kept"] = []
    return result


def answer_baseline(question: str) -> dict:
    """Как в d22: top-5 сразу в контекст, без фильтра."""
    retrieved = retrieve(question, TOP_K_AFTER)
    return _answer_with_chunks(question, retrieved, retrieved)


def answer_threshold(question: str) -> dict:
    retrieved = retrieve(question, TOP_K_BEFORE)
    kept = filter_by_threshold(retrieved)
    return _answer_with_chunks(question, retrieved, kept)


def answer_llm_rerank(question: str) -> dict:
    retrieved = retrieve(question, TOP_K_BEFORE)
    kept = llm_rerank(question, retrieved)
    return _answer_with_chunks(question, retrieved, kept)


def answer_rewrite_filter(question: str) -> dict:
    rewritten = rewrite_query(question)
    retrieved = retrieve(rewritten, TOP_K_BEFORE)
    kept = filter_by_threshold(retrieved)
    result = _answer_with_chunks(question, retrieved, kept)
    result["rewritten_query"] = rewritten
    return result


MODES = {
    "no_rag": answer_no_rag,
    "baseline": answer_baseline,
    "threshold": answer_threshold,
    "llm_rerank": answer_llm_rerank,
    "rewrite_filter": answer_rewrite_filter,
}


def answer(question: str, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"Неизвестный режим: {mode}. Доступны: {list(MODES)}")
    result = MODES[mode](question)
    result["mode"] = mode
    return result
