import asyncio
import json
import os
import uuid

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

PORT = int(os.environ.get("PORT", 8000))

# хранилище очередей: session_id -> Queue с JSON-RPC ответами
sessions: dict[str, asyncio.Queue] = {}

TOOLS = [
    {
        "name": "get_weather",
        "description": "Возвращает текущую погоду в указанном городе.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Название города на английском (например: Moscow, London)"
                }
            },
            "required": ["city"]
        }
    }
]


async def get_weather(city: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://wttr.in/{city}?format=j1", timeout=10)
        response.raise_for_status()
    data = response.json()
    current = data["current_condition"][0]
    return (
        f"Погода в {city}:\n"
        f"  Состояние: {current['weatherDesc'][0]['value']}\n"
        f"  Температура: {current['temp_C']}°C (ощущается как {current['FeelsLikeC']}°C)\n"
        f"  Влажность: {current['humidity']}%\n"
        f"  Ветер: {current['windspeedKmph']} км/ч"
    )


async def handle_sse(request: Request):
    """Открывает SSE-соединение и держит его пока клиент подключён."""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    sessions[session_id] = queue

    async def event_stream():
        # сообщаем клиенту куда слать POST-запросы
        yield f"event: endpoint\ndata: /messages?sessionId={session_id}\n\n"
        try:
            while True:
                message = await queue.get()
                yield f"event: message\ndata: {json.dumps(message)}\n\n"
        finally:
            sessions.pop(session_id, None)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


async def handle_message(request: Request):
    """Принимает JSON-RPC запросы от клиента и кладёт ответ в SSE-очередь."""
    session_id = request.query_params.get("sessionId")
    if session_id not in sessions:
        return Response("Session not found", status_code=404)

    body = await request.json()
    method = body.get("method")
    msg_id = body.get("id")
    queue = sessions[session_id]

    if method == "initialize":
        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "Weather Server", "version": "1.0"}
            }
        })

    elif method == "notifications/initialized":
        pass  # уведомление, ответ не нужен

    elif method == "tools/list":
        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOLS}
        })

    elif method == "tools/call":
        name = body["params"]["name"]
        arguments = body["params"]["arguments"]
        if name == "get_weather":
            result_text = await get_weather(arguments["city"])
        else:
            result_text = f"Неизвестный инструмент: {name}"

        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": result_text}],
                "isError": False
            }
        })

    else:
        await queue.put({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        })

    return Response(status_code=202)


app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Route("/messages", endpoint=handle_message, methods=["POST"]),
])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
