import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

PORT = int(os.environ.get("PORT", 8002))
RESULTS_DIR = Path("/opt/d19/results")
RESULTS_DIR.mkdir(exist_ok=True)

sessions: dict[str, asyncio.Queue] = {}


# ─── Инструменты ───────────────────────────────────────────────────────────────

async def tool_search(query: str) -> str:
    """Ищет статью в Wikipedia и возвращает её текст."""
    headers = {"User-Agent": "pipeline-mcp-agent/1.0 (educational project)"}
    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        # 1. Находим заголовок статьи
        r = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query, "limit": 1, "format": "json"},
        )
        r.raise_for_status()
        titles = r.json()[1]
        if not titles:
            return f"Ничего не найдено по запросу: {query}"

        title = titles[0]

        # 2. Получаем текст статьи
        r2 = await client.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
        )
        r2.raise_for_status()
        article = r2.json()

    return f"Заголовок: {article['title']}\n\n{article.get('extract', '')}"


def tool_summarize(text: str, max_sentences: int = 3) -> str:
    """Сжимает текст до N предложений."""
    # Убираем строку заголовка
    lines = [l for l in text.split("\n") if l and not l.startswith("Заголовок:")]
    content = " ".join(lines)

    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    sentences = [s for s in sentences if len(s) > 20][:max_sentences]

    return " ".join(sentences)


def tool_save_to_file(filename: str, content: str) -> str:
    """Сохраняет текст в файл в папке results/."""
    safe = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
    if not safe.endswith(".txt"):
        safe += ".txt"

    path = RESULTS_DIR / safe
    path.write_text(content, encoding="utf-8")
    return f"Сохранено: {path}  ({len(content)} символов)"


TOOLS = [
    {
        "name": "search",
        "description": "Ищет информацию в Wikipedia по запросу и возвращает текст статьи.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос на английском"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "summarize",
        "description": "Сжимает длинный текст до краткого резюме из N предложений.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Текст для сжатия"},
                "max_sentences": {"type": "integer", "description": "Кол-во предложений (по умолчанию 3)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "save_to_file",
        "description": "Сохраняет текст в файл. Возвращает путь к файлу.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Имя файла (без расширения)"},
                "content": {"type": "string", "description": "Содержимое файла"},
            },
            "required": ["filename", "content"],
        },
    },
]


# ─── MCP транспорт (SSE) ───────────────────────────────────────────────────────

async def handle_sse(request: Request):
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    sessions[session_id] = queue

    async def event_stream():
        yield f"event: endpoint\ndata: /messages?sessionId={session_id}\n\n"
        try:
            while True:
                message = await queue.get()
                yield f"event: message\ndata: {json.dumps(message)}\n\n"
        finally:
            sessions.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def handle_message(request: Request):
    session_id = request.query_params.get("sessionId")
    if session_id not in sessions:
        return Response("Session not found", status_code=404)

    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")
    queue = sessions[session_id]

    if method == "initialize":
        await queue.put({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Pipeline MCP", "version": "1.0"},
            },
        })

    elif method == "notifications/initialized":
        pass

    elif method == "tools/list":
        await queue.put({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})

    elif method == "tools/call":
        name = body["params"]["name"]
        args = body["params"].get("arguments", {})
        try:
            if name == "search":
                result = await tool_search(args["query"])
            elif name == "summarize":
                result = tool_summarize(args["text"], args.get("max_sentences", 3))
            elif name == "save_to_file":
                result = tool_save_to_file(args["filename"], args["content"])
            else:
                result = f"Неизвестный инструмент: {name}"
        except Exception as e:
            result = f"Ошибка: {e}"

        await queue.put({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {"content": [{"type": "text", "text": result}], "isError": False},
        })

    else:
        await queue.put({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        })

    return Response(status_code=202)


app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Route("/messages", endpoint=handle_message, methods=["POST"]),
])

if __name__ == "__main__":
    print(f"Pipeline MCP сервер запущен: http://localhost:{PORT}")
    print(f"Результаты сохраняются в: {RESULTS_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
