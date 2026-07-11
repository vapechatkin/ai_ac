"""
d30: RAG-агент рекомендатор книг на базе Ollama.

Эндпоинты:
  GET  /health          — статус сервиса и модели
  POST /chat            — сообщение (с сессией и RAG)
  DELETE /session/{id}  — очистить историю сессии
  GET  /sessions        — список активных сессий

Ограничения:
  - Rate limit: 10 запросов/минуту на IP
  - Max context: 20 сообщений в истории сессии
  - Timeout: 120 секунд на ответ модели
"""

import json
import os
import time
import uuid
from collections import defaultdict
from typing import Optional

import faiss
import numpy as np
import requests
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

OLLAMA_URL  = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL       = "qwen2.5:3b"
EMBED_MODEL = "nomic-embed-text"
API_TOKEN   = os.getenv("AI_TOKEN")   # если не задан — auth отключена (dev-режим)
TOP_K       = 6

BASE       = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE, "data", "books.faiss")
META_FILE  = os.path.join(BASE, "data", "books_meta.json")

security = HTTPBearer(auto_error=False)
MAX_HISTORY = 20
RATE_LIMIT  = 10
RATE_WINDOW = 60

SYSTEM = """Ты — литературный советник. Тебе передан список реальных книг из базы данных.
Твоя задача — выбрать ОДНУ лучшую книгу из предложенных и порекомендовать её.

Отвечай строго в этом формате:

📖 **Название** (Автор, год)
[2-3 предложения почему именно эта книга подходит под запрос пользователя]

Похожие из базы:
• Название (Автор)
• Название (Автор)
• Название (Автор)

ВАЖНО: используй ТОЛЬКО книги из предоставленного списка. Не выдумывай книги."""

app = FastAPI(title="Book Recommender AI", version="1.0")


@app.on_event("startup")
def warmup():
    try:
        requests.post(f"{OLLAMA_URL}/api/embed",
                      json={"model": EMBED_MODEL, "input": ["warmup"]}, timeout=60)
        requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model": MODEL, "messages": [{"role": "user", "content": "hi"}],
            "stream": False, "options": {"num_predict": 1},
        }, timeout=120)
    except Exception:
        pass

# ── Загрузка индекса при старте ──────────────────────────────────────────────
if not os.path.exists(INDEX_FILE):
    raise RuntimeError(f"Индекс не найден: {INDEX_FILE}")

_index = faiss.read_index(INDEX_FILE)
with open(META_FILE, encoding="utf-8") as f:
    _meta = json.load(f)

# ── Хранилище сессий и rate limiter ──────────────────────────────────────────
sessions: dict[str, list] = {}
rate_store: dict[str, list] = defaultdict(list)


# ── Auth ──────────────────────────────────────────────────────────────────────
def check_auth(credentials: HTTPAuthorizationCredentials):
    if not API_TOKEN:
        return
    if not credentials or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")


# ── Rate limiting ─────────────────────────────────────────────────────────────
def check_rate_limit(ip: str) -> bool:
    now = time.time()
    rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]
    if len(rate_store[ip]) >= RATE_LIMIT:
        return False
    rate_store[ip].append(now)
    return True


# ── RAG ───────────────────────────────────────────────────────────────────────
def embed(text: str) -> np.ndarray:
    resp = requests.post(f"{OLLAMA_URL}/api/embed",
                         json={"model": EMBED_MODEL, "input": [text]}, timeout=60)
    resp.raise_for_status()
    vec = np.array(resp.json()["embeddings"], dtype="float32")
    faiss.normalize_L2(vec)
    return vec


def retrieve(query: str) -> list:
    vec = embed(query)
    scores, ids = _index.search(vec, TOP_K)
    books = []
    for score, idx in zip(scores[0], ids[0]):
        if idx != -1:
            books.append({**_meta[idx], "score": float(score)})
    return books


def build_context(books: list) -> str:
    lines = []
    for b in books:
        lines.append(
            f"- **{b['title']}** ({b['author']}, {b['year']}) "
            f"[{', '.join(b['genre'])}]\n  {b['description']}"
        )
    return "\n".join(lines)


# ── Модели запросов ───────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_len: int
    response_time: float
    books_found: int


# ── Эндпоинты ─────────────────────────────────────────────────────────────────
@app.get("/")
def index():
    return FileResponse(os.path.join(BASE, "chat.html"))


@app.get("/health")
def health(credentials: HTTPAuthorizationCredentials = Security(security)):
    check_auth(credentials)
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in resp.json().get("models", [])]
        model_ok = any(MODEL in m for m in models)
        embed_ok = any(EMBED_MODEL in m for m in models)
    except Exception:
        return JSONResponse(status_code=503, content={
            "status": "error", "ollama": False,
        })
    return {
        "status": "ok",
        "ollama": True,
        "model": MODEL,
        "model_loaded": model_ok,
        "embed_model": EMBED_MODEL,
        "embed_loaded": embed_ok,
        "books_indexed": len(_meta),
        "active_sessions": len(sessions),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request,
         credentials: HTTPAuthorizationCredentials = Security(security)):
    check_auth(credentials)
    ip = request.client.host

    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail=f"Rate limit: max {RATE_LIMIT} req/min")

    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = []
    history = sessions[sid]

    # RAG: ищем релевантные книги по запросу пользователя
    t0 = time.time()
    try:
        books = retrieve(req.message)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Embed error: {e}")

    context = build_context(books)
    user_msg = f"Запрос пользователя: {req.message}\n\nДоступные книги из базы:\n{context}"

    history.append({"role": "user", "content": user_msg})
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM}] + history

    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model":    MODEL,
            "messages": messages,
            "stream":   False,
            "options":  {"temperature": 0.5, "num_predict": 400, "num_ctx": 8192},
        }, timeout=180)
        resp.raise_for_status()
    except requests.Timeout:
        history.pop()
        raise HTTPException(status_code=504, detail="Model timeout (>180s)")
    except Exception as e:
        history.pop()
        raise HTTPException(status_code=502, detail=str(e))

    reply = resp.json()["message"]["content"].strip()
    elapsed = round(time.time() - t0, 2)

    history.append({"role": "assistant", "content": reply})
    sessions[sid] = history

    return ChatResponse(
        reply=reply,
        session_id=sid,
        history_len=len(history),
        response_time=elapsed,
        books_found=len(books),
    )


@app.delete("/session/{session_id}")
def delete_session(session_id: str,
                   credentials: HTTPAuthorizationCredentials = Security(security)):
    check_auth(credentials)
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@app.get("/sessions")
def list_sessions(credentials: HTTPAuthorizationCredentials = Security(security)):
    check_auth(credentials)
    return {
        "count": len(sessions),
        "sessions": [
            {"id": sid, "messages": len(hist)} for sid, hist in sessions.items()
        ],
    }
