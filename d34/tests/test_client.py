import asyncio
from pathlib import Path

from mcp_client import ProjectMCPClient


def test_real_mcp_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("from widget import Widget\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Widget\n", encoding="utf-8")

    async def roundtrip():
        async with ProjectMCPClient(tmp_path) as client:
            tools = await client.tool_definitions()
            result = await client.call("search_text", {"query": "Widget"})
        return tools, result

    tools, result = asyncio.run(roundtrip())

    assert {tool["name"] for tool in tools} >= {"list_files", "search_text", "read_files", "write_file", "diff_changes"}
    assert len(result["matches"]) == 2
