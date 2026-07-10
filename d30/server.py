"""
d30: приватный AI-сервис на базе Ollama.

Эндпоинты:
  GET  /health          — статус сервиса и модели
  POST /chat            — отправить сообщение (с сессией)
  DELETE /session/{id}  — очистить историю сессии

Ограничения:
  - Rate limit: 10 запросов/минуту на IP
  - Max context: 20 сообщений в истории сессии
  - Timeout: 120 секунд на ответ модели
"""

import time
import uuid
from collections import defaultdict
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

OLLAMA_URL  = "http://localhost:11434"
MODEL       = "qwen2.5:3b"
MAX_HISTORY = 20        # максимум сообщений в сессии
RATE_LIMIT  = 10        # запросов в минуту на IP
RATE_WINDOW = 60        # секунд

app = FastAPI(title="Private AI Service", version="1.0")

# ── Хранилище сессий и rate limiter ─────────────────────────────────────────
sessions: dict[str, list] = {}
rate_store: dict[str, list] = defaultdict(list)

SYSTEM = (
    "Ты — полезный AI-ассистент. Отвечай чётко и по делу. "
    "Если не знаешь ответа — скажи об этом прямо."
)


# ── Rate limiting ────────────────────────────────────────────────────────────
def check_rate_limit(ip: str) -> bool:
    now = time.time()
    rate_store[ip] = [t for t in rate_store[ip] if now - t < RATE_WINDOW]
    if len(rate_store[ip]) >= RATE_LIMIT:
        return False
    rate_store[ip].append(now)
    return True


# ── Модели запросов ──────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    history_len: int
    response_time: float


# ── Эндпоинты ────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in resp.json().get("models", [])]
        model_ok = any(MODEL in m for m in models)
    except Exception:
        return JSONResponse(status_code=503, content={
            "status": "error", "ollama": False, "model": MODEL, "model_loaded": False
        })
    return {
        "status": "ok",
        "ollama": True,
        "model": MODEL,
        "model_loaded": model_ok,
        "active_sessions": len(sessions),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    ip = request.client.host

    # Rate limit
    if not check_rate_limit(ip):
        raise HTTPException(status_code=429, detail=f"Rate limit: max {RATE_LIMIT} req/min")

    # Сессия
    sid = req.session_id or str(uuid.uuid4())
    if sid not in sessions:
        sessions[sid] = []

    history = sessions[sid]
    history.append({"role": "user", "content": req.message})

    # Обрезаем историю до MAX_HISTORY
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    messages = [{"role": "system", "content": SYSTEM}] + history

    # Запрос к Ollama
    t0 = time.time()
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json={
            "model":    MODEL,
            "messages": messages,
            "stream":   False,
            "options":  {"temperature": 0.7, "num_predict": 512, "num_ctx": 8192},
        }, timeout=120)
        resp.raise_for_status()
    except requests.Timeout:
        history.pop()
        raise HTTPException(status_code=504, detail="Model timeout (>120s)")
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
    )


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    del sessions[session_id]
    return {"status": "deleted", "session_id": session_id}


@app.get("/sessions")
def list_sessions():
    return {
        "count": len(sessions),
        "sessions": [
            {"id": sid, "messages": len(hist)} for sid, hist in sessions.items()
        ],
    }
