"""Plotting and analysis for active learning experiments.

Generates efficiency curves and comparative analysis of annotation strategies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger


@dataclass
class EfficiencyCurve:
    """Data for a single efficiency curve (one experiment configuration)."""

    name: str
    strategy: str
    metric_name: str  # Which metric this curve represents
    x_values: list[int]  # Annotations used
    y_values: list[float]  # Performance values for the metric

    # Full metrics history for multi-metric analysis
    metrics_history: list[dict[str, float]] = field(default_factory=list)

    # Additional derived metrics
    final_annotations: int = 0
    final_performance: float = 0.0
    area_under_curve: float = 0.0
    annotations_to_target: int | None = None  # Annotations to reach target performance
    target_threshold: float = 0.80  # Target performance threshold

    def __post_init__(self):
        """Calculate derived metrics after initialization."""
        self._calculate_metrics()

    @classmethod
    def from_experiment_result(
        cls,
        result_dict: dict[str, Any],
        metric_name: str | None = None,
    ) -> "EfficiencyCurve":
        """Create from experiment result dictionary.

        Args:
            result_dict: Experiment result from ExperimentResult.to_dict()
            metric_name: Which metric to use for the Y-axis (default: primary_metric from config)
        """
        config = result_dict.get("config", {})

        # Determine which metric to plot
        actual_metric_name = metric_name or config.get("primary_metric", "detection_f1")

        x = result_dict.get("annotations_used", [])

        # Get Y values for the specified metric
        metrics_history = result_dict.get("metrics_history", [])
        if metrics_history:
            y = [m.get(actual_metric_name, 0.0) for m in metrics_history]
        else:
            # Fallback to primary_metric_scores for backwards compatibility
            y = result_dict.get("primary_metric_scores", [])

        final_metrics = result_dict.get("final_metrics", {})

        curve = cls(
            name=config.get("name", "unknown"),
            strategy=config.get("strategy", "unknown"),
            metric_name=actual_metric_name,
            x_values=x,
            y_values=y,
            metrics_history=metrics_history,
            final_annotations=result_dict.get("total_annotations_used", 0),
            final_performance=final_metrics.get(actual_metric_name, 0.0),
        )

        return curve

    def _calculate_metrics(self) -> None:
        """Calculate derived metrics."""
        if not self.x_values or not self.y_values:
            return

        # Area under curve (trapezoidal rule)
        self.area_under_curve = float(np.trapezoid(self.y_values, self.x_values))

        # Annotations to reach target threshold
        for i, (x, y) in enumerate(zip(self.x_values, self.y_values)):
            if y >= self.target_threshold:
                self.annotations_to_target = x
                break

    def get_metric_at_annotations(self, annotations: int) -> float:
        """Get performance at a specific annotation count."""
        for i, x in enumerate(self.x_values):
            if x >= annotations:
                return self.y_values[i] if i < len(self.y_values) else 0.0
        return self.y_values[-1] if self.y_values else 0.0


def plot_efficiency_curves(
    curves: list[EfficiencyCurve],
    output_path: str | Path,
    title: str = "Active Learning Efficiency",
    xlabel: str = "Human Annotations Used",
    ylabel: str = "Mean IoU",
    figsize: tuple[int, int] = (12, 8),
    show_auc: bool = True,
    show_target_line: float | None = 0.80,
) -> Path:
    """Plot multiple efficiency curves for comparison.

    Args:
        curves: List of efficiency curves to plot
        output_path: Where to save the plot
        title: Plot title
        xlabel: X-axis label
        ylabel: Y-axis label
        figsize: Figure size (width, height)
        show_auc: Include area-under-curve in legend
        show_target_line: Draw horizontal line at this performance level

    Returns:
        Path to saved plot
    """
    fig, ax = plt.subplots(figsize=figsize)

    # Color palette
    colors = plt.get_cmap("tab10")(np.linspace(0, 1, len(curves)))

    for i, curve in enumerate(curves):
        if not curve.x_values or not curve.y_values:
            logger.warning(f"Skipping empty curve: {curve.name}")
            continue

        # Build label
        label = curve.name.replace("_", " ").title()
        if show_auc:
            label += f" (AUC={curve.area_under_curve:.1f})"

        # Plot
        ax.plot(
            curve.x_values,
            curve.y_values,
            marker="o",
            markersize=4,
            linewidth=2,
            label=label,
            color=colors[i],
        )

        # Mark final point
        if curve.x_values and curve.y_values:
            ax.scatter(
                [curve.x_values[-1]],
                [curve.y_values[-1]],
                s=100,
                marker="*",
                color=colors[i],
                zorder=5,
            )

    # Add target line
    if show_target_line:
        ax.axhline(
            y=show_target_line,
            color="gray",
            linestyle="--",
            linewidth=1,
            alpha=0.7,
            label=f"Target ({show_target_line * 100:.0f}% IoU)",
        )

    # Labels and title
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight="bold")

    # Legend
    ax.legend(loc="lower right", fontsize=10)

    # Grid
    ax.grid(True, alpha=0.3, linestyle=":")

    # Limits
    ax.set_xlim(left=0)
    ax.set_ylim(0, 1.0)

    plt.tight_layout()

    # Save
    output_path = Path(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info(f"Saved efficiency curve plot to {output_path}")
    return output_path


def plot_strategy_comparison(
    curves: list[EfficiencyCurve],
    output_path: str | Path,
    metric: str = "annotations_to_target",
    target_threshold: float = 0.80,
    title: str = "Strategy Comparison",
) -> Path:
    """Create a bar chart comparing strategies on a specific metric.

    Args:
        curves: List of efficiency curves
        output_path: Where to save the plot
        metric: Which metric to compare ('annotations_to_target', 'final_performance', 'auc')
        target_threshold: Target performance threshold for annotation counting
        title: Plot title

    Returns:
        Path to saved plot
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Extract data
    names = []
    values = []
    colors = []

    for curve in curves:
        names.append(curve.name.replace("_", " ").title())

        if metric == "annotations_to_target":
            # Check if target was reached
            target_reached = False
            target_annotations = None
            for x, y in zip(curve.x_values, curve.y_values):
                if y >= target_threshold:
                    target_reached = True
                    target_annotations = x
                    break

            if target_reached and target_annotations is not None:
                val = target_annotations
                colors.append("green")
            else:
                # Penalty for not reaching target
                val = curve.final_annotations * 1.5 if curve.final_annotations > 0 else 999
                colors.append("red")
            values.append(val)

        elif metric == "final_performance":
            values.append(curve.final_performance)
            colors.append("blue")

        elif metric == "auc":
            values.append(curve.area_under_curve)
            colors.append("purple")

        else:
            values.append(0)
            colors.append("gray")

    # Create bars
    bars = ax.bar(range(len(names)), values, color=colors, alpha=0.7, edgecolor="black")

    # Add value labels on bars
    for i, (bar, val) in enumerate(zip(bars, values)):
        height = bar.get_height()
        label = f"{val:.1f}" if metric != "final_performance" else f"{val:.2f}"
        if metric == "annotations_to_target" and colors[i] == "red":
            label = "N/A"
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )

    # Labels
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right")

    if metric == "annotations_to_target":
        ax.set_ylabel(f"Annotations to Reach {target_threshold * 100:.0f}% Performance", fontsize=12)
        ax.set_title(f"{title}\n(Lower is Better)", fontsize=14, fontweight="bold")
    elif metric == "final_performance":
        ax.set_ylabel("Final Performance", fontsize=12)
        ax.set_title(f"{title}\n(Higher is Better)", fontsize=14, fontweight="bold")
    elif metric == "auc":
        ax.set_ylabel("Area Under Efficiency Curve", fontsize=12)
        ax.set_title(f"{title}\n(Higher is Better)", fontsize=14, fontweight="bold")

    ax.grid(True, axis="y", alpha=0.3, linestyle=":")

    plt.tight_layout()

    # Save
    output_path = Path(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info(f"Saved strategy comparison plot to {output_path}")
    return output_path


def create_summary_table(
    curves: list[EfficiencyCurve],
    output_path: str | Path,
    target_threshold: float = 0.80,
) -> Path:
    """Create a markdown summary table of experiment results.

    Args:
        curves: List of efficiency curves
        output_path: Where to save the table
        target_threshold: Target performance threshold

    Returns:
        Path to saved table
    """
    target_pct = int(target_threshold * 100)

    lines = [
        "# Active Learning Experiment Results\n",
        f"| Strategy | Annotations Used | Final Performance | AUC | Annotations to {target_pct}% |",
        "|----------|------------------|-------------------|-----|-----------------------|",
    ]

    for curve in curves:
        # Check if target was reached
        target_annotations = None
        for x, y in zip(curve.x_values, curve.y_values):
            if y >= target_threshold:
                target_annotations = x
                break

        annotations_target_str = str(target_annotations) if target_annotations else "Not reached"

        lines.append(
            f"| {curve.name} | {curve.final_annotations} | {curve.final_performance:.3f} | {curve.area_under_curve:.1f} | {annotations_target_str} |"
        )

    # Add interpretation
    lines.extend(
        [
            "\n## Key Findings\n",
            "### Most Efficient Strategy\n",
        ]
    )

    # Find best by different metrics
    def get_target_annotations(curve: EfficiencyCurve) -> int:
        for x, y in zip(curve.x_values, curve.y_values):
            if y >= target_threshold:
                return x
        return curve.final_annotations * 10  # Penalty

    by_annotations = min(curves, key=get_target_annotations)
    by_performance = max(curves, key=lambda c: c.final_performance)
    by_auc = max(curves, key=lambda c: c.area_under_curve)

    best_target = get_target_annotations(by_annotations)
    best_target_str = str(best_target) if best_target < by_annotations.final_annotations * 5 else "N/A"

    lines.extend(
        [
            f"- **Fewest annotations to {target_pct}%**: {by_annotations.name} ({best_target_str} annotations)",
            f"- **Highest final performance**: {by_performance.name} ({by_performance.final_performance:.3f})",
            f"- **Best area under curve**: {by_auc.name} ({by_auc.area_under_curve:.1f})",
        ]
    )

    output_path = Path(output_path)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Saved summary table to {output_path}")
    return output_path


def analyze_experiment_results(
    results_file: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """Analyze experiment results and generate all plots and reports.

    Args:
        results_file: Path to JSON results file
        output_dir: Directory to save outputs

    Returns:
        Dict mapping output type to saved file path
    """
    results_file = Path(results_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load results
    with open(results_file) as f:
        data = json.load(f)

    # Convert to curves
    curves = [EfficiencyCurve.from_experiment_result(result) for result in data.values()]

    outputs = {}

    # Generate efficiency curve plot
    outputs["efficiency_curve"] = plot_efficiency_curves(
        curves=curves,
        output_path=output_dir / "efficiency_curves.png",
        title="Active Learning Efficiency Curves",
    )

    # Generate strategy comparison
    outputs["strategy_comparison"] = plot_strategy_comparison(
        curves=curves,
        output_path=output_dir / "strategy_comparison.png",
        metric="annotations_to_80",
        title="Annotations Required to Reach 80% IoU",
    )

    # Generate final performance comparison
    outputs["final_performance"] = plot_strategy_comparison(
        curves=curves,
        output_path=output_dir / "final_performance.png",
        metric="final_performance",
        title="Final Segmentation Performance",
    )

    # Generate summary table
    outputs["summary_table"] = create_summary_table(
        curves=curves,
        output_path=output_dir / "results_summary.md",
    )

    return outputs


def plot_annotation_distribution(
    results_file: str | Path,
    output_path: str | Path,
) -> Path:
    """Plot how annotations were distributed across classes.

    Args:
        results_file: Path to JSON results file
        output_path: Where to save the plot

    Returns:
        Path to saved plot
    """
    with open(results_file) as f:
        data = json.load(f)

    fig, axes = plt.subplots(1, len(data), figsize=(6 * len(data), 6))

    if len(data) == 1:
        axes = [axes]

    for idx, (name, result) in enumerate(data.items()):
        ax = axes[idx]

        # Extract annotations by class from step details
        class_counts: dict[str, int] = {}

        for step in result.get("step_details", []):
            # This is a simplification - real implementation would track per-class
            metrics = step.get("metrics", {})
            for cls, count in metrics.get("per_class_annotations", {}).items():
                class_counts[cls] = class_counts.get(cls, 0) + count

        if class_counts:
            classes = list(class_counts.keys())
            counts = list(class_counts.values())

            ax.pie(counts, labels=classes, autopct="%1.1f%%", startangle=90)
            ax.set_title(f"{name}\nAnnotation Distribution")
        else:
            ax.text(0.5, 0.5, "No class data", ha="center", va="center")
            ax.set_title(f"{name}")

    plt.tight_layout()

    output_path = Path(output_path)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    logger.info(f"Saved annotation distribution plot to {output_path}")
    return output_path


def create_interactive_report(
    results_file: str | Path,
    output_path: str | Path,
) -> Path:
    """Create an HTML report with interactive plots.

    Args:
        results_file: Path to JSON results file
        output_path: Where to save the HTML report

    Returns:
        Path to saved report
    """
    with open(results_file) as f:
        data = json.load(f)

    # Build HTML
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Active Learning Experiment Results</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #333; }
            .metric { display: inline-block; margin: 10px; padding: 15px; 
                     background: #f0f0f0; border-radius: 5px; }
            .metric-value { font-size: 24px; font-weight: bold; color: #2196F3; }
            .metric-label { font-size: 12px; color: #666; }
        </style>
    </head>
    <body>
        <h1>Active Learning Experiment Results</h1>
    """

    # Add summary metrics
    html += '<div id="summary">'

    for name, result in data.items():
        config = result.get("config", {})
        html += f"""
        <div class="metric">
            <div class="metric-label">{name}</div>
            <div class="metric-value">{result.get("final_performance", 0):.3f} IoU</div>
            <div class="metric-label">{result.get("total_annotations_used", 0)} annotations</div>
        </div>
        """

    html += "</div>"

    # Add plotly chart
    html += '<div id="efficiency-plot" style="width:100%;height:500px;"></div>'

    # Build plotly data
    traces = []
    for name, result in data.items():
        x = result.get("annotations_used", [])
        y = result.get("performance_scores", [])
        traces.append(
            {
                "x": x,
                "y": y,
                "mode": "lines+markers",
                "name": name,
                "line": {"width": 2},
            }
        )

    html += f"""
    <script>
        var traces = {json.dumps(traces)};
        var layout = {{
            title: 'Active Learning Efficiency Curves',
            xaxis: {{title: 'Human Annotations Used'}},
            yaxis: {{title: 'Mean IoU', range: [0, 1]}},
            hovermode: 'closest'
        }};
        Plotly.newPlot('efficiency-plot', traces, layout);
    </script>
    </body>
    </html>
    """

    output_path = Path(output_path)
    with open(output_path, "w") as f:
        f.write(html)

    logger.info(f"Saved interactive report to {output_path}")
    return output_path
