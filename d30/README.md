# d30: Book Recommender AI — деплой на VPS

RAG-агент рекомендатор книг на базе Ollama (`qwen2.5:3b` + `nomic-embed-text`).
100 реальных книг в FAISS-индексе. Деплой на Yandex Cloud VM.

## Публичный доступ

**URL:** `https://89.169.140.120.sslip.io/ai`  
**Token:** `c068430753f3e77f6a079b5df87e115a4701887c70d8b72363f9fa53a93fde8a`

Открыть чат в браузере: <https://89.169.140.120.sslip.io/ai>  
В настройках (⚙) вставить токен.

## API

```bash
TOKEN=c068430753f3e77f6a079b5df87e115a4701887c70d8b72363f9fa53a93fde8a
BASE=https://89.169.140.120.sslip.io/ai

# Health check
curl -H "Authorization: Bearer $TOKEN" $BASE/health

# Запрос
curl -X POST $BASE/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "хочу детектив"}'

# Продолжить сессию
curl -X POST $BASE/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "что-то похожее", "session_id": "<id из предыдущего ответа>"}'
```

## Локальный запуск

```bash
# Нужен Ollama с моделями
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

cd d30
pip install fastapi uvicorn requests faiss-cpu numpy
uvicorn server:app --port 8000
# Чат: открыть chat.html в браузере
```

## Инфраструктура

- VM: Yandex Cloud, 4 CPU / 8 GB RAM, IP `89.169.140.120`
- Docker Compose в `/Users/viktor/monopoly/infra/prod/`
- Caddy проксирует `/ai/*` → контейнер `ai:8000`
- Ollama запущен на хосте VM (`OLLAMA_HOST=0.0.0.0:11434`)
- Скорость ответа: ~65 секунд (CPU-only inference)
