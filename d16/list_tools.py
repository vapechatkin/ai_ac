import asyncio
import os

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client

load_dotenv()

# Удалённый MCP-сервер Яндекс Поиска
MCP_URL = "https://d5de9siimt9bkld7viic.emzafcgx.apigw.yandexcloud.net:3000/sse"

# Ключи берутся из .env
API_KEY = os.environ.get("YANDEX_API_KEY", "")
FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "")

if not API_KEY or not FOLDER_ID:
    raise ValueError(
        "Создайте файл .env с:\n"
        "  YANDEX_API_KEY=<ваш_ключ>\n"
        "  YANDEX_FOLDER_ID=<ваш_folder_id>"
    )

HEADERS = {
    "ApiKey": API_KEY,
    "FolderId": FOLDER_ID,
}


async def main():
    print(f"Подключаемся к MCP-серверу: {MCP_URL}\n")

    async with sse_client(MCP_URL, headers=HEADERS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Соединение установлено.")

            result = await session.list_tools()

            print(f"\nДоступные инструменты ({len(result.tools)}):")
            print("-" * 40)
            for tool in result.tools:
                print(f"Название: {tool.name}")
                print(f"Описание: {tool.description}")
                print("-" * 40)


asyncio.run(main())
