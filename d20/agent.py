import asyncio
import json
import os

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

# Три удалённых MCP-сервера
SERVERS = [
    {"name": "weather",   "url": "https://weather-mcp-server-anvu.onrender.com"},
    {"name": "scheduler", "url": "http://157.22.253.10:8001"},
    {"name": "pipeline",  "url": "http://157.22.253.10:8002"},
]

claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Глобальный счётчик id и словарь ожидающих futures
pending: dict[int, asyncio.Future] = {}
msg_id_counter = 0


def next_id() -> int:
    global msg_id_counter
    msg_id_counter += 1
    return msg_id_counter


async def listen_sse(client: httpx.AsyncClient, base_url: str, endpoint_future: asyncio.Future):
    async with client.stream("GET", f"{base_url}/sse") as response:
        event_type = None
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event_type = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data = line.removeprefix("data:").strip()
                if event_type == "endpoint":
                    endpoint_future.set_result(data)
                elif event_type == "message":
                    msg = json.loads(data)
                    future = pending.pop(msg.get("id"), None)
                    if future:
                        future.set_result(msg)


async def send(client: httpx.AsyncClient, base_url: str, post_path: str, method: str, params: dict = None) -> dict:
    msg_id = next_id()
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    pending[msg_id] = future
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        body["params"] = params
    await client.post(f"{base_url}{post_path}", json=body)
    return await future


async def notify(client: httpx.AsyncClient, base_url: str, post_path: str, method: str):
    await client.post(f"{base_url}{post_path}", json={"jsonrpc": "2.0", "method": method})


async def connect_server(server: dict) -> tuple[httpx.AsyncClient, str, list, asyncio.Task]:
    """Подключается к MCP-серверу, инициализирует сессию, возвращает инструменты."""
    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=90, read=None, write=30, pool=30))
    loop = asyncio.get_event_loop()
    endpoint_future = loop.create_future()

    sse_task = asyncio.create_task(listen_sse(client, server["url"], endpoint_future))
    post_path = await asyncio.wait_for(endpoint_future, timeout=90)

    await send(client, server["url"], post_path, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "multi-server-agent", "version": "1.0"},
    })
    await notify(client, server["url"], post_path, "notifications/initialized")

    tools_resp = await send(client, server["url"], post_path, "tools/list")
    tools = tools_resp["result"]["tools"]

    return client, post_path, tools, sse_task


async def run_agent():
    # ── Подключаемся ко всем серверам ──────────────────────────────────────────
    tool_router: dict[str, tuple[httpx.AsyncClient, str, str]] = {}  # tool → (client, url, post_path)
    all_claude_tools = []
    sse_tasks = []

    for server in SERVERS:
        print(f"[{server['name']}] подключаюсь к {server['url']} ...")
        client, post_path, tools, sse_task = await connect_server(server)
        sse_tasks.append(sse_task)
        print(f"[{server['name']}] инструменты: {[t['name'] for t in tools]}")

        for tool in tools:
            tool_router[tool["name"]] = (client, server["url"], post_path)
            all_claude_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["inputSchema"],
            })

    print(f"\nВсего инструментов из {len(SERVERS)} серверов: {len(all_claude_tools)}\n")

    # ── Задача для агента ───────────────────────────────────────────────────────
    user_message = (
        "Выполни длинный флоу из 6 шагов:\n"
        "1. Найди информацию о 'Mars exploration' через search\n"
        "2. Получи текущую погоду в Москве через get_weather\n"
        "3. Запусти мониторинг погоды для Moscow каждые 60 секунд через schedule_collection\n"
        "4. Сделай резюме статьи о Mars из 4 предложений через summarize\n"
        "5. Покажи список активных расписаний через list_schedules\n"
        "6. Сохрани итоговый отчёт (резюме + текущая погода в Москве) в файл 'mars_moscow_report' через save_to_file\n"
        "Выполняй строго по порядку, передавая результат каждого шага следующему где нужно."
    )

    print(f"Задача агента:\n{user_message}\n{'─'*60}\n")
    messages = [{"role": "user", "content": user_message}]

    # ── Цикл агента ────────────────────────────────────────────────────────────
    while True:
        response = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            tools=all_claude_tools,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            break

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        tool_results = []

        for tool_use in tool_uses:
            client, url, post_path = tool_router[tool_use.name]
            server_name = next(s["name"] for s in SERVERS if s["url"] == url)

            # Показываем аргументы без длинных текстов
            preview_input = {
                k: (v[:70] + "..." if isinstance(v, str) and len(v) > 70 else v)
                for k, v in tool_use.input.items()
            }
            print(f"[{server_name}] → {tool_use.name}({preview_input})")

            call_resp = await send(client, url, post_path, "tools/call", {
                "name": tool_use.name,
                "arguments": tool_use.input,
            })
            result_text = call_resp["result"]["content"][0]["text"]
            preview = result_text[:120] + "..." if len(result_text) > 120 else result_text
            print(f"           ← {preview}\n")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_text,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    final = next(b.text for b in response.content if b.type == "text")
    print(f"{'─'*60}\nАгент: {final}")

    for task in sse_tasks:
        task.cancel()


if __name__ == "__main__":
    asyncio.run(run_agent())
