import asyncio
import json
import os
import sqlite3
import uuid
from datetime import datetime

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

PORT = int(os.environ.get("PORT", 8001))
DB_PATH = os.path.join(os.path.dirname(__file__), "weather_data.db")

sessions: dict[str, asyncio.Queue] = {}
schedule_tasks: dict[str, asyncio.Task] = {}  # city_lower -> Task


# ─── База данных ───────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            temp_c REAL,
            humidity INTEGER,
            wind_kmph INTEGER,
            description TEXT,
            collected_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            city TEXT PRIMARY KEY,
            interval_seconds INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_reading(city: str, w: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO readings (city, temp_c, humidity, wind_kmph, description, collected_at) VALUES (?, ?, ?, ?, ?, ?)",
        (city, w["temp_c"], w["humidity"], w["wind_kmph"], w["description"], datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


import re


# ─── Сбор данных ───────────────────────────────────────────────────────────────

async def fetch_weather(city: str) -> dict:
    # wttr.in компактный формат: "+18°C|68%|↘10km/h|Partly cloudy"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://wttr.in/{city}",
            params={"format": "%t|%h|%w|%C"},
        )
        r.raise_for_status()
    temp_str, humidity_str, wind_str, description = r.text.strip().split("|")
    temp_c = float(re.sub(r"[^0-9.\-]", "", temp_str))
    humidity = int(re.sub(r"[^0-9]", "", humidity_str))
    wind_kmph = int(re.sub(r"[^0-9]", "", wind_str) or "0")
    return {
        "temp_c": temp_c,
        "humidity": humidity,
        "wind_kmph": wind_kmph,
        "description": description.strip(),
    }


async def collect_loop(city: str, interval_seconds: int):
    """Бесконечный цикл: собирает данные сразу, затем по расписанию."""
    while True:
        try:
            weather = await fetch_weather(city)
            save_reading(city, weather)
            print(f"[scheduler] {datetime.utcnow().strftime('%H:%M:%S')} {city}: {weather['temp_c']}°C, {weather['description']}")
        except Exception as e:
            print(f"[scheduler] Ошибка для {city}: {e}")
        await asyncio.sleep(interval_seconds)


# ─── MCP-инструменты ───────────────────────────────────────────────────────────

async def tool_schedule_collection(city: str, interval_seconds: int) -> str:
    key = city.lower()
    if key in schedule_tasks and not schedule_tasks[key].done():
        schedule_tasks[key].cancel()

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO schedules (city, interval_seconds, created_at) VALUES (?, ?, ?)",
        (city, interval_seconds, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    schedule_tasks[key] = asyncio.create_task(collect_loop(city, interval_seconds))
    return f"Запущен сбор данных для {city} каждые {interval_seconds} сек. Первый замер — сейчас."


async def tool_stop_collection(city: str) -> str:
    key = city.lower()
    if key in schedule_tasks and not schedule_tasks[key].done():
        schedule_tasks[key].cancel()
        del schedule_tasks[key]

    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM schedules WHERE city = ?", (city,))
    conn.commit()
    conn.close()
    return f"Сбор данных для {city} остановлен."


async def tool_get_summary(city: str) -> str:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT temp_c, humidity, wind_kmph, description, collected_at FROM readings WHERE city = ? ORDER BY collected_at DESC LIMIT 50",
        (city,)
    ).fetchall()
    conn.close()

    if not rows:
        return f"Нет данных для {city}. Сначала запустите schedule_collection."

    temps = [r[0] for r in rows]
    humidities = [r[1] for r in rows]
    latest = rows[0]

    return (
        f"Сводка по {city} ({len(rows)} замеров):\n"
        f"  Последний замер ({latest[4][:19]} UTC): {latest[3]}, {latest[0]}°C\n"
        f"  Температура: мин {min(temps)}°C / макс {max(temps)}°C / среднее {round(sum(temps)/len(temps), 1)}°C\n"
        f"  Влажность (среднее): {round(sum(humidities)/len(humidities), 1)}%"
    )


async def tool_list_schedules() -> str:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT city, interval_seconds, created_at FROM schedules").fetchall()
    conn.close()

    if not rows:
        return "Нет сохранённых расписаний."

    lines = ["Расписания:"]
    for city, interval, created_at in rows:
        key = city.lower()
        active = key in schedule_tasks and not schedule_tasks[key].done()
        status = "активно" if active else "остановлено"
        lines.append(f"  {city}: каждые {interval} сек ({status}), с {created_at[:19]} UTC")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "schedule_collection",
        "description": "Запускает периодический фоновый сбор данных о погоде для города.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Город на английском (Moscow, London, Tokyo)"},
                "interval_seconds": {"type": "integer", "description": "Интервал сбора в секундах (например 30)"},
            },
            "required": ["city", "interval_seconds"],
        },
    },
    {
        "name": "stop_collection",
        "description": "Останавливает периодический сбор данных для города.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Название города"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_summary",
        "description": "Возвращает агрегированную сводку по накопленным данным о погоде для города.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Название города"},
            },
            "required": ["city"],
        },
    },
    {
        "name": "list_schedules",
        "description": "Показывает все сохранённые расписания сбора данных.",
        "inputSchema": {
            "type": "object",
            "properties": {},
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
                "serverInfo": {"name": "Weather Scheduler", "version": "1.0"},
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
            if name == "schedule_collection":
                result = await tool_schedule_collection(args["city"], args["interval_seconds"])
            elif name == "stop_collection":
                result = await tool_stop_collection(args["city"])
            elif name == "get_summary":
                result = await tool_get_summary(args["city"])
            elif name == "list_schedules":
                result = await tool_list_schedules()
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


init_db()

app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Route("/messages", endpoint=handle_message, methods=["POST"]),
])

if __name__ == "__main__":
    print(f"Weather Scheduler MCP запущен на порту {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
