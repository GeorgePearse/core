"""Compare the offline source excerpts with a read-only harness checkout."""

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def verify_checkout(checkout: Path) -> None:
    """Verify pinned source bytes and current relevant definitions without importing services."""
    manifest = json.loads((FIXTURES / "upstream_contract.json").read_text())
    for entry in manifest["sources"]:
        source = subprocess.check_output(
            [
                "git",
                "-C",
                str(checkout),
                "show",
                f"{manifest['commit']}:{entry['path']}",
            ]
        )
        if hashlib.sha256(source).hexdigest() != entry["sha256"]:
            raise ValueError(f"pinned source hash differs: {entry['path']}")
        pinned = ast.parse(source)
        current = ast.parse((checkout / entry["path"]).read_text())
        for name, excerpt in entry["definitions"].items():
            expected = ast.dump(ast.parse(excerpt).body[0], include_attributes=False)
            for label, module in (("pinned", pinned), ("current", current)):
                found = []
                for node in module.body:
                    node_name = getattr(node, "name", None)
                    if isinstance(node, ast.Assign) and isinstance(
                        node.targets[0], ast.Name
                    ):
                        node_name = node.targets[0].id
                    if node_name == name:
                        found.append(ast.dump(node, include_attributes=False))
                if found != [expected]:
                    raise ValueError(f"{label} contract drift: {entry['path']}:{name}")
    for filename in ("upstream_links.json", "upstream_surface.json"):
        data = json.loads((FIXTURES / filename).read_text())
        fixture = data["provenance"]
        source = subprocess.check_output(
            [
                "git",
                "-C",
                str(checkout),
                "show",
                f"{fixture['commit']}:{fixture['path']}",
            ]
        )
        if hashlib.sha256(source).hexdigest() != fixture["source_sha256"]:
            raise ValueError(f"fixture source hash differs: {filename}")
        function = next(
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == fixture["test"]
        )
        for node in function.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                if name in data and (
                    node.value is None or ast.literal_eval(node.value) != data[name]
                ):
                    raise ValueError(f"fixture values differ: {filename}:{name}")


def main() -> None:
    """Expose a bounded contract verification command for the source owner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    verify_checkout(args.checkout)
    print("Pinned source hashes and current contract definitions match.")


if __name__ == "__main__":
    main()
