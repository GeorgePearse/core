"""A compact MCP surface for a frontier model supervising local learners."""

import argparse
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from modelmode.workspace import Workspace


def make_server(root: str) -> FastMCP:
    """Bind tools to one explicit trusted workspace and expose them over stdio."""
    workspace = Workspace(root)
    mcp = FastMCP(
        "ModelMode",
        instructions=(
            "Create learned tools from reviewed text or numeric features. Inspect the catalog, "
            "create an immutable dataset, learn bounded candidates and review validation errors. "
            "Only call evaluate once tuning is finished: it opens test and seals the dataset. "
            "Publish a successful evaluated model, then use predict for cheap routine execution. "
            "The MCP host is the supervisor; this server never calls a hosted LLM. "
            "Do not relabel teacher examples as independent ground truth. Scores are not calibrated confidence."
        ),
    )
    read_only = ToolAnnotations(readOnlyHint=True)
    mutable = ToolAnnotations(readOnlyHint=False, destructiveHint=False)

    @mcp.tool(annotations=read_only)
    def catalog() -> dict:
        """List candidate families, optional dependencies and CPU execution mode."""
        return workspace.catalog()

    @mcp.tool(annotations=mutable)
    def create_dataset(name: str, rows: list[dict[str, Any]], seed: int = 42) -> dict:
        """Freeze examples: id, label, text OR features, optional group/split/label_source.

        Splits are train/validation/test. Supply every split or omit all for
        automatic grouped 60/20/20 splitting. Teacher labels are train-only.
        """
        return workspace.create_dataset(name, rows, seed)

    @mcp.tool(annotations=read_only)
    def list_datasets() -> list[dict]:
        """List dataset IDs, input schemas, partition counts and sealing state."""
        return workspace.list_datasets()

    @mcp.tool(annotations=mutable)
    def learn(
        dataset_id: str,
        candidates: list[str] | None = None,
        metric: str = "macro_f1",
        min_score: float = 0.0,
        objective: str = "quality",
        budget_seconds: float = 120,
        seed: int = 42,
        execution: str = "local",
        training: dict[str, Any] | None = None,
    ) -> dict:
        """Start a background local or Modal search; poll get_run. One active job per workspace.

        objective is quality or fastest_at_quality (requires positive min_score).
        The budget includes process startup, downloads, fitting and validation.
        execution=modal uses the deployed single-GPU worker. training accepts
        epochs, batch_size, learning_rate, max_length, and initialization
        (pretrained or random). Fine-tuning updates the whole encoder.
        """
        return workspace.learn(
            dataset_id,
            candidates,
            metric,
            min_score,
            objective,
            budget_seconds,
            seed,
            execution,
            training,
        )

    @mcp.tool(annotations=read_only)
    def get_run(run_id: str) -> dict:
        """Read progress, candidate failures, validation results and measured costs."""
        return workspace.get_run(run_id)

    @mcp.tool(annotations=read_only)
    def list_runs() -> list[dict]:
        """Compare persistent search records and recover IDs after reconnecting."""
        return workspace.list_runs()

    @mcp.tool(annotations=mutable)
    def cancel(run_id: str) -> dict:
        """Request termination of a running job without discarding its evidence."""
        return workspace.cancel(run_id)

    @mcp.tool(annotations=read_only)
    def review(run_id: str, limit: int = 20) -> list[dict]:
        """Inspect selected-model validation errors; never exposes test examples."""
        return workspace.review(run_id, limit)

    @mcp.tool(annotations=mutable)
    def evaluate(run_id: str) -> dict:
        """FINAL test evaluation: seals this dataset against any further tuning.

        Only the validation-selected candidate and dummy baseline are evaluated.
        Repeating this call returns the same saved result.
        """
        return workspace.evaluate(run_id)

    @mcp.tool(annotations=mutable)
    def publish(run_id: str, name: str, abstain_below: float = 0.0) -> dict:
        """Register a versioned capability after final evaluation passes its floor."""
        return workspace.publish(run_id, name, abstain_below)

    @mcp.tool(annotations=read_only)
    def list_capabilities() -> list[dict]:
        """Discover published learned tools and their version histories."""
        return workspace.list_capabilities()

    @mcp.tool(annotations=read_only)
    def predict(name: str, examples: list[Any], version: int | None = None) -> dict:
        """Run a named capability on text strings or numeric vectors.

        Pin version for repeatability. An abstained result should be sent to the
        supervising model or a reviewer instead of being accepted automatically.
        """
        return workspace.predict(name, examples, version)

    return mcp


def main() -> None:
    """Run a local stdio server; stdout is reserved for the MCP protocol."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", required=True, help="Trusted local artifact directory"
    )
    args = parser.parse_args()
    make_server(args.root).run(transport="stdio")


if __name__ == "__main__":
    main()
