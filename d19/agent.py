import asyncio
import json
import os
import sys

import anthropic
import httpx
from dotenv import load_dotenv

load_dotenv()

SERVER_URL = "http://157.22.253.10:8002"
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


async def run_pipeline(topic: str):
    async with httpx.AsyncClient(timeout=30) as client:
        loop = asyncio.get_event_loop()
        endpoint_future = loop.create_future()
        sse_task = asyncio.create_task(listen_sse(client, endpoint_future))
        post_path = await endpoint_future

        await send(client, post_path, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pipeline-agent", "version": "1.0"},
        })
        await notify(client, post_path, "notifications/initialized")

        tools_response = await send(client, post_path, "tools/list")
        tools = tools_response["result"]["tools"]
        claude_tools = [mcp_tool_to_claude(t) for t in tools]
        print(f"Инструменты: {[t['name'] for t in tools]}")

        user_message = (
            f"Выполни пайплайн из трёх шагов:\n"
            f"1. Найди информацию о '{topic}' через search\n"
            f"2. Сделай резюме из 5 предложений через summarize\n"
            f"3. Сохрани резюме в файл '{topic.replace(' ', '_')}' через save_to_file\n"
            f"Выполняй шаги последовательно, передавая результат каждого шага следующему."
        )
        print(f"\nЗадача: {user_message}\n")

        messages = [{"role": "user", "content": user_message}]

        while True:
            response = claude.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                tools=claude_tools,
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []
            for tool_use in tool_uses:
                print(f"[{tool_use.name}] вызов: { {k: v[:80] + '...' if isinstance(v, str) and len(v) > 80 else v for k, v in tool_use.input.items()} }")
                call_response = await send(client, post_path, "tools/call", {
                    "name": tool_use.name,
                    "arguments": tool_use.input,
                })
                result_text = call_response["result"]["content"][0]["text"]
                preview = result_text[:120] + "..." if len(result_text) > 120 else result_text
                print(f"[{tool_use.name}] результат: {preview}\n")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_text,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        final = next(b.text for b in response.content if b.type == "text")
        print(f"Агент: {final}")
        sse_task.cancel()


if __name__ == "__main__":
    topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "quantum computing"
    asyncio.run(run_pipeline(topic))
