"""A JSON CLI mirroring the Python and MCP lifecycle."""

import argparse
import json

from modelmode.workspace import Workspace


def main() -> None:
    """Call any public lifecycle operation with a JSON object of arguments."""
    parser = argparse.ArgumentParser(
        description="ModelMode: learned tools, local first"
    )
    parser.add_argument("--root", required=True)
    parser.add_argument(
        "operation",
        choices=[
            "catalog",
            "create_dataset",
            "describe_dataset",
            "list_datasets",
            "learn",
            "get_run",
            "list_runs",
            "wait",
            "review",
            "evaluate",
            "publish",
            "predict",
            "list_capabilities",
            "cancel",
        ],
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--json", default="{}", help="JSON object of keyword arguments")
    source.add_argument(
        "--file", help="File containing a JSON object of keyword arguments"
    )
    args = parser.parse_args()
    if args.file:
        with open(args.file) as stream:
            arguments = json.load(stream)
    else:
        arguments = json.loads(args.json)
    result = getattr(Workspace(args.root), args.operation)(**arguments)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
