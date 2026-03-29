import argparse
import subprocess
import sys
import os
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich import box

# Initialize Rich Console
console = Console()


def run_command(args):
    """Wrapper for genesis_launch (Hydra)"""
    # Process args to match genesis_launch bash script logic
    processed_args = []
    keys_to_process = {"database", "evolution", "task", "cluster", "variant"}

    for arg in args.extra_args:
        if "=" in arg:
            key, val = arg.split("=", 1)
            if key in keys_to_process and "@" not in key:
                processed_args.append(f"{key}@_global_={val}")
            else:
                processed_args.append(arg)
        else:
            processed_args.append(arg)

    # Pass all extra arguments to the hydra launcher
    cmd = [sys.executable, "-m", "genesis.launch_hydra"] + processed_args
    console.print(
        f"[bold green]🚀 Running Genesis Experiment:[/bold green] {' '.join(cmd)}"
    )
    subprocess.run(cmd)


def ui_command(args):
    """Start the WebUI frontend"""
    frontend_dir = Path(__file__).parent / "webui" / "frontend"
    if not frontend_dir.exists():
        console.print(
            f"[bold red]Error:[/bold red] Frontend directory not found at {frontend_dir}"
        )
        return

    console.print("[bold orange1]🎨 Starting Genesis WebUI...[/bold orange1]")
    console.print(f"Working directory: [dim]{frontend_dir}[/dim]")

    if not (frontend_dir / "node_modules").exists():
        console.print("[yellow]📦 Installing dependencies...[/yellow]")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)

    subprocess.run(["npm", "run", "dev"], cwd=frontend_dir)


def list_command(args):
    """List recent experiments"""
    results_dir = Path("results")
    if not results_dir.exists():
        console.print("[yellow]No results directory found.[/yellow]")
        return

    table = Table(title="Genesis Experiments", box=box.ROUNDED, border_style="orange1")
    table.add_column("Task", style="cyan")
    table.add_column("Run ID", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right", style="bold green")

    # Gather data
    experiments = []
    for task_dir in sorted(results_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        for run_dir in sorted(task_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue

            status = "Running"
            score = "-"
            status_style = "yellow"

            # Check for completion/metrics
            best_metrics = run_dir / "best" / "results" / "metrics.json"
            if best_metrics.exists():
                status = "Completed"
                status_style = "green"
                try:
                    m = json.loads(best_metrics.read_text())
                    val = m.get("combined_score", 0)
                    score = f"{val:.4f}"
                except:
                    pass
            elif (run_dir / ".hydra").exists() and not (
                run_dir / "evolution_db.sqlite"
            ).exists():
                # Heuristic for failed/empty runs
                pass

            experiments.append(
                {
                    "task": task_dir.name,
                    "run_id": run_dir.name,
                    "status": status,
                    "status_style": status_style,
                    "score": score,
                }
            )

    # Add rows to table
    limit = args.limit if args.limit > 0 else len(experiments)
    for exp in experiments[:limit]:
        table.add_row(
            exp["task"],
            exp["run_id"],
            f"[{exp['status_style']}]{exp['status']}[/{exp['status_style']}]",
            exp["score"],
        )

    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Genesis CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run an evolution experiment")
    run_parser.add_argument(
        "extra_args", nargs=argparse.REMAINDER, help="Hydra arguments"
    )
    run_parser.set_defaults(func=run_command)

    # UI command
    ui_parser = subparsers.add_parser("ui", help="Start the WebUI")
    ui_parser.set_defaults(func=ui_command)

    # List command
    list_parser = subparsers.add_parser("list", help="List experiments")
    list_parser.add_argument(
        "-n", "--limit", type=int, default=10, help="Limit number of results"
    )
    list_parser.set_defaults(func=list_command)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
