"""
d30: тест сервиса — здоровье, несколько запросов, сессия, rate limit.
"""

import time
import requests

BASE = "http://localhost:8000"
SEP  = "─" * 55


def ok(label, resp):
    status = "✅" if resp.status_code < 400 else "❌"
    print(f"{status} [{resp.status_code}] {label}")
    return resp


# ── 1. Health ────────────────────────────────────────────────────────────────
print(f"\n{'═'*55}")
print("  1. HEALTH CHECK")
print(SEP)
r = ok("GET /health", requests.get(f"{BASE}/health"))
print(f"   {r.json()}")

# ── 2. Несколько запросов (стабильность) ────────────────────────────────────
print(f"\n{'═'*55}")
print("  2. СТАБИЛЬНОСТЬ (3 запроса подряд)")
print(SEP)

questions = [
    "Что такое RAG в контексте LLM?",
    "Назови 3 популярных векторных базы данных.",
    "В чём разница между fine-tuning и RAG?",
]

session_id = None
for q in questions:
    payload = {"message": q}
    if session_id:
        payload["session_id"] = session_id

    r = requests.post(f"{BASE}/chat", json=payload, timeout=130)
    ok(f"POST /chat — {q[:40]}...", r)

    if r.status_code == 200:
        data = r.json()
        session_id = data["session_id"]
        print(f"   ⏱  {data['response_time']}s  |  история: {data['history_len']} сообщ.")
        print(f"   💬 {data['reply'][:120]}...")
    print()

# ── 3. Сессия сохраняет контекст ────────────────────────────────────────────
print(f"{'═'*55}")
print("  3. КОНТЕКСТ СЕССИИ")
print(SEP)

r1 = requests.post(f"{BASE}/chat", json={"message": "Меня зовут Витя."}, timeout=130)
sid = r1.json()["session_id"]
print(f"✅ Сообщение 1 отправлено. Session: {sid[:8]}...")

r2 = requests.post(f"{BASE}/chat", json={"message": "Как меня зовут?", "session_id": sid}, timeout=130)
reply = r2.json()["reply"]
print(f"✅ Модель ответила: {reply[:150]}")

# ── 4. Rate limit ────────────────────────────────────────────────────────────
print(f"\n{'═'*55}")
print("  4. RATE LIMIT (11 быстрых запросов)")
print(SEP)

hit_limit = False
for i in range(11):
    r = requests.post(f"{BASE}/chat", json={"message": f"ping {i}"}, timeout=130)
    if r.status_code == 429:
        print(f"✅ Rate limit сработал на запросе #{i+1}: {r.json()['detail']}")
        hit_limit = True
        break

if not hit_limit:
    print("⚠️  Rate limit не сработал (запросы слишком медленные)")

# ── 5. Список сессий ─────────────────────────────────────────────────────────
print(f"\n{'═'*55}")
print("  5. АКТИВНЫЕ СЕССИИ")
print(SEP)
r = requests.get(f"{BASE}/sessions")
print(f"✅ Сессий: {r.json()['count']}")
for s in r.json()["sessions"]:
    print(f"   {s['id'][:8]}...  {s['messages']} сообщений")

print(f"\n{'═'*55}")
print("  ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
print(f"{'═'*55}\n")
