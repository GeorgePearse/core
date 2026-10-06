import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

# Initialize server
server = Server("genesis-mcp")


def get_results_root() -> Path:
    """Get the results directory path."""
    # Assumes running from project root or standard structure
    # Fallback to current directory if 'results' exists, else relative to module
    cwd_results = Path(os.getcwd()) / "results"
    if cwd_results.exists():
        return cwd_results

    # Default fallback (might need adjustment based on install location)
    return Path(os.getcwd()) / "results"


@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    return [
        Tool(
            name="list_experiments",
            description="List recent evolution experiments and their status",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 10,
                    }
                },
            },
        ),
        Tool(
            name="get_experiment_metrics",
            description="Get metrics for a specific experiment run",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_path": {
                        "type": "string",
                        "description": "Relative path to run directory (e.g., genesis_mask_to_seg/2025...)",
                    }
                },
                "required": ["run_path"],
            },
        ),
        Tool(
            name="launch_experiment",
            description="Launch a new evolution experiment",
            inputSchema={
                "type": "object",
                "properties": {
                    "variant": {
                        "type": "string",
                        "description": "Variant name (e.g., mask_to_seg_rust_example)",
                    },
                    "generations": {
                        "type": "integer",
                        "description": "Number of generations (optional override)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description for tracking",
                    },
                },
                "required": ["variant"],
            },
        ),
        Tool(
            name="read_best_code",
            description="Read the best discovered code from an experiment",
            inputSchema={
                "type": "object",
                "properties": {
                    "run_path": {
                        "type": "string",
                        "description": "Relative path to run directory",
                    }
                },
                "required": ["run_path"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict
) -> List[TextContent | ImageContent | EmbeddedResource]:
    results_root = get_results_root()

    if name == "list_experiments":
        runs = []
        if results_root.exists():
            for task_dir in results_root.iterdir():
                if task_dir.is_dir():
                    for run_dir in task_dir.iterdir():
                        if (
                            run_dir.is_dir()
                            and (run_dir / "experiment_config.yaml").exists()
                        ):
                            # Try to find status
                            metrics = {}
                            # Check for best/results/metrics.json (completed/successful run)
                            best_metrics = run_dir / "best" / "results" / "metrics.json"

                            status = "Unknown"
                            score = "N/A"

                            if best_metrics.exists():
                                try:
                                    m = json.loads(best_metrics.read_text())
                                    score = str(
                                        m.get("combined_score")
                                        or m.get("mean_iou")
                                        or "N/A"
                                    )
                                    status = "Completed (Best found)"
                                except:
                                    pass

                            runs.append(
                                {
                                    "task": task_dir.name,
                                    "run_id": run_dir.name,
                                    "path": str(run_dir.relative_to(results_root)),
                                    "status": status,
                                    "score": score,
                                }
                            )

        # Sort by date (folder name usually contains timestamp)
        runs.sort(key=lambda x: x["run_id"], reverse=True)
        return [
            TextContent(
                type="text",
                text=json.dumps(runs[: arguments.get("limit", 10)], indent=2),
            )
        ]

    elif name == "get_experiment_metrics":
        run_path = arguments["run_path"]
        # Check 'best' metrics first
        best_metrics = results_root / run_path / "best" / "results" / "metrics.json"
        if best_metrics.exists():
            return [TextContent(type="text", text=best_metrics.read_text())]

        # Fallback to searching for latest generation
        run_dir = results_root / run_path
        if run_dir.exists():
            gens = sorted(
                [
                    d
                    for d in run_dir.iterdir()
                    if d.is_dir() and d.name.startswith("gen_")
                ],
                key=lambda x: int(x.name.split("_")[1]),
            )
            if gens:
                last_gen_metrics = gens[-1] / "results" / "metrics.json"
                if last_gen_metrics.exists():
                    return [TextContent(type="text", text=last_gen_metrics.read_text())]

        return [TextContent(type="text", text="Metrics file not found.")]

    elif name == "launch_experiment":
        variant = arguments["variant"]
        gens = arguments.get("generations")

        cmd = ["python3", "-m", "genesis.launch_hydra", f"variant@_global_={variant}"]
        if gens:
            cmd.append(f"evo_config.num_generations={gens}")

        # Launch in background
        log_file = Path("/tmp") / f"genesis_mcp_{variant}.log"
        with open(log_file, "w") as f:
            proc = subprocess.Popen(
                cmd, stdout=f, stderr=subprocess.STDOUT, start_new_session=True
            )

        return [
            TextContent(
                type="text",
                text=f"Started experiment '{variant}' with PID {proc.pid}.\nLogs: {log_file}",
            )
        ]

    elif name == "read_best_code":
        run_path = arguments["run_path"]
        best_dir = results_root / run_path / "best"
        if best_dir.exists():
            for ext in ["py", "rs", "cpp", "cu"]:
                code_file = best_dir / f"main.{ext}"
                if code_file.exists():
                    return [TextContent(type="text", text=code_file.read_text())]

        return [TextContent(type="text", text="Best code not found.")]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1], server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
