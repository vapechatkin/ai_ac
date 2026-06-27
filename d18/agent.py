import asyncio
import json
import os
import sys

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = "http://157.22.253.10:8001"
claude = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

pending: dict[int, asyncio.Future] = {}
msg_id_counter = 0


def next_id() -> int:
    global msg_id_counter
    msg_id_counter += 1
    return msg_id_counter


async def listen_sse(client: httpx.AsyncClient, endpoint_future: asyncio.Future):
    async with client.stream("GET", f"{SERVER_URL}/sse") as response:
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


async def send(client: httpx.AsyncClient, post_path: str, method: str, params: dict = None) -> dict:
    msg_id = next_id()
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    pending[msg_id] = future
    body = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params:
        body["params"] = params
    await client.post(f"{SERVER_URL}{post_path}", json=body)
    return await future


async def notify(client: httpx.AsyncClient, post_path: str, method: str):
    await client.post(f"{SERVER_URL}{post_path}", json={"jsonrpc": "2.0", "method": method})


def mcp_tool_to_claude(tool: dict) -> dict:
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["inputSchema"],
    }


async def run_agent(user_message: str):
    async with httpx.AsyncClient(timeout=30) as client:
        loop = asyncio.get_event_loop()
        endpoint_future = loop.create_future()
        sse_task = asyncio.create_task(listen_sse(client, endpoint_future))
        post_path = await endpoint_future
        print(f"Сессия: {SERVER_URL}{post_path}")
        await send(client, post_path, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "scheduler-agent", "version": "1.0"}
        })
        await notify(client, post_path, "notifications/initialized")
        tools_response = await send(client, post_path, "tools/list")
        tools = tools_response["result"]["tools"]
        claude_tools = [mcp_tool_to_claude(t) for t in tools]
        print(f"Инструменты: {[t['name'] for t in tools]}")
        print(f"\nПользователь: {user_message}")
        messages = [{"role": "user", "content": user_message}]
        while True:
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                tools=claude_tools,
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                break
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            for tool_use in tool_uses:
                print(f"\n[агент вызывает] {tool_use.name}({tool_use.input})")
                call_response = await send(client, post_path, "tools/call", {
                    "name": tool_use.name,
                    "arguments": tool_use.input,
                })
                result_text = call_response["result"]["content"][0]["text"]
                print(f"[результат]\n{result_text}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_text,
                })
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        final = next(b.text for b in response.content if b.type == "text")
        print(f"\nАгент: {final}")
        sse_task.cancel()


MESSAGES = {
    "schedule": (
        "Запусти периодический сбор данных о погоде для Москвы и Лондона каждые 30 секунд. "
        "Потом покажи список активных расписаний."
    ),
    "summary": (
        "Покажи список всех расписаний и агрегированную сводку погоды для Москвы и Лондона."
    ),
    "stop": (
        "Останови сбор данных для Москвы и Лондона."
    ),
}

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "schedule"
    if mode not in MESSAGES:
        print(f"Режимы: {list(MESSAGES.keys())}")
        sys.exit(1)
    asyncio.run(run_agent(MESSAGES[mode]))
