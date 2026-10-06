"""Snapshot testing for generated code."""

import json
from pathlib import Path
from typing import Optional

from evaluator.models import AgentResponse, Assertion, AssertionResult


class SnapshotManager:
    """Manages snapshots for snapshot testing."""

    def __init__(self, snapshot_dir: str = ".snapshots") -> None:
        """Initialize snapshot manager.

        Args:
            snapshot_dir: Directory to store snapshots
        """
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(exist_ok=True)

    def get_snapshot_path(self, snapshot_name: str) -> Path:
        """Get path for snapshot file.

        Args:
            snapshot_name: Name of the snapshot

        Returns:
            Path to snapshot file
        """
        return self.snapshot_dir / f"{snapshot_name}.snapshot.json"

    def load_snapshot(self, snapshot_name: str) -> Optional[dict]:
        """Load snapshot from file.

        Args:
            snapshot_name: Name of the snapshot

        Returns:
            Snapshot dict or None if not found
        """
        path = self.get_snapshot_path(snapshot_name)
        if not path.exists():
            return None

        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def save_snapshot(self, snapshot_name: str, data: dict) -> None:
        """Save snapshot to file.

        Args:
            snapshot_name: Name of the snapshot
            data: Data to snapshot
        """
        path = self.get_snapshot_path(snapshot_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def compare_snapshots(self, snapshot1: dict, snapshot2: dict) -> tuple[bool, list[str]]:
        """Compare two snapshots.

        Args:
            snapshot1: First snapshot
            snapshot2: Second snapshot

        Returns:
            Tuple of (are_equal, differences)
        """
        differences = []

        # Check keys
        keys1 = set(snapshot1.keys())
        keys2 = set(snapshot2.keys())

        missing_in_2 = keys1 - keys2
        extra_in_2 = keys2 - keys1

        if missing_in_2:
            differences.append(f"Missing in new snapshot: {', '.join(sorted(missing_in_2))}")
        if extra_in_2:
            differences.append(f"Extra in new snapshot: {', '.join(sorted(extra_in_2))}")

        # Check values
        for key in keys1 & keys2:
            if snapshot1[key] != snapshot2[key]:
                differences.append(f"Value changed for '{key}'")

        return len(differences) == 0, differences


class SnapshotEvaluator:
    """Evaluates snapshot assertions."""

    def __init__(self, snapshot_dir: str = ".snapshots") -> None:
        """Initialize snapshot evaluator.

        Args:
            snapshot_dir: Directory for snapshots
        """
        self.manager = SnapshotManager(snapshot_dir)

    def evaluate(
        self,
        assertion: Assertion,
        response: AgentResponse,
        update_snapshots: bool = False,
    ) -> AssertionResult:
        """Evaluate snapshot assertion.

        Args:
            assertion: The snapshot assertion
            response: The agent response
            update_snapshots: If True, update snapshot instead of comparing

        Returns:
            AssertionResult
        """
        snapshot_name = assertion.metadata.get("snapshot_name")
        if not snapshot_name:
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message="No snapshot_name in assertion metadata",
            )

        # Extract data to snapshot
        fields = assertion.metadata.get("fields", ["full_response"])
        snapshot_data = {}

        for field in fields:
            match field:
                case "full_response":
                    snapshot_data["full_response"] = response.full_response
                case "generated_code":
                    snapshot_data["generated_code"] = response.generated_code
                case "generated_commands":
                    snapshot_data["generated_commands"] = response.generated_commands
                case "tool_calls":
                    snapshot_data["tool_calls"] = response.tool_calls
                case _:
                    pass

        if update_snapshots:
            self.manager.save_snapshot(snapshot_name, snapshot_data)
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"✓ Snapshot updated: {snapshot_name}",
            )

        # Load existing snapshot
        existing = self.manager.load_snapshot(snapshot_name)
        if existing is None:
            # First time - save snapshot
            self.manager.save_snapshot(snapshot_name, snapshot_data)
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"✓ Snapshot created: {snapshot_name}",
            )

        # Compare snapshots
        are_equal, differences = self.manager.compare_snapshots(existing, snapshot_data)

        if are_equal:
            return AssertionResult(
                assertion=assertion,
                passed=True,
                message=f"✓ Snapshot matches: {snapshot_name}",
            )
        else:
            message = f"✗ Snapshot mismatch for {snapshot_name}:\n" + "\n".join(
                f"  - {diff}" for diff in differences
            )
            return AssertionResult(
                assertion=assertion,
                passed=False,
                message=message,
                evidence={"differences": differences},
            )
