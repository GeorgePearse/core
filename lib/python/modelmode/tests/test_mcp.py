"""Exercise actual JSON-RPC over stdio, including a host restart."""

import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_stdio_lifecycle(tmp_path: Path, rows: list[dict]) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "modelmode.server", "--root", str(tmp_path)]
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            assert {"learn", "evaluate", "publish", "predict", "cancel"} <= tools

            async def invoke(name: str, arguments: dict) -> dict:
                result = await session.call_tool(name, arguments)
                assert not result.isError, result
                return json.loads(result.content[0].text)

            dataset = await invoke("create_dataset", {"name": "stdio", "rows": rows})
            run = await invoke(
                "learn",
                {
                    "dataset_id": dataset["dataset_id"],
                    "candidates": ["tfidf_word"],
                    "budget_seconds": 45,
                },
            )
            for _ in range(100):
                state = await invoke("get_run", {"run_id": run["run_id"]})
                if state["status"] in {"succeeded", "failed", "cancelled", "timed_out"}:
                    break
                await asyncio.sleep(0.2)
            assert state["status"] == "succeeded", state
            await invoke("evaluate", {"run_id": run["run_id"]})
            await invoke("publish", {"run_id": run["run_id"], "name": "route"})
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.call_tool(
                "predict", {"name": "route", "examples": ["payment payment"]}
            )
            assert not result.isError
            assert (
                json.loads(result.content[0].text)["predictions"][0]["label"]
                == "payment"
            )
