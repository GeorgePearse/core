#!/usr/bin/env python3
"""Collect and store performance metrics from benchmarks.

This script runs benchmarks and appends results to metrics.json in JSONL format,
compatible with the metrics visualization website.
"""

import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional


def get_system_info() -> dict:
    """Get host system information."""
    try:
        cpu_info = platform.processor() or "Unknown"
    except Exception:
        cpu_info = "Unknown"

    try:
        # Get memory in GB
        import psutil

        mem_gb = psutil.virtual_memory().total / (1024**3)
        mem_str = f"{mem_gb:.1f} GB"
    except Exception:
        mem_str = "Unknown"

    return {
        "os": platform.platform(),
        "cpu": cpu_info,
        "mem": mem_str,
        "python_version": platform.python_version(),
    }


def get_git_revision() -> Optional[str]:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:7]  # Short hash
    except Exception:
        return None


def run_benchmarks() -> dict:
    """Run pytest benchmarks and collect results.

    Returns:
        Dictionary mapping benchmark names to [value, unit] pairs
    """
    print("🏃 Running benchmarks...")

    # Use pytest-benchmark with JSON output
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as f:
        json_output = f.name

    try:
        # Run pytest with benchmark plugin
        result = subprocess.run(
            [
                "pytest",
                "benchmarks/benchmark_copy_paste.py",
                "-v",
                f"--benchmark-json={json_output}",
                "--benchmark-disable-gc",
                "--benchmark-warmup=on",
                "-x",  # Stop on first failure
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )

        if result.returncode != 0:
            print("⚠️ Some benchmarks failed:")
            print(result.stdout)
            print(result.stderr)

        # Parse benchmark results
        with open(json_output) as f:
            data = json.load(f)

        metrics = {}

        # Extract metrics from benchmark results
        for bench in data.get("benchmarks", []):
            name = bench.get("name", "unknown")
            # Extract scenario name from test name
            if "::" in name:
                scenario = name.split("::")[-1]
            else:
                scenario = name

            stats = bench.get("stats", {})

            # Use median as the main metric
            median_time = stats.get("median", 0) * 1000  # Convert to ms

            if median_time > 0:
                # Store time in milliseconds
                key = f"{scenario}/time_ms"
                metrics[key] = [round(median_time, 2), "ms"]

                # Calculate throughput (images per second)
                throughput = 1000 / median_time if median_time > 0 else 0
                key = f"{scenario}/throughput"
                metrics[key] = [round(throughput, 2), "img/s"]

            # Store min/max for reference
            max_val = stats.get("max", 0)

            if max_val > 0:
                key = f"{scenario}/max_ms"
                metrics[key] = [round(max_val * 1000, 2), "ms"]

        return metrics

    finally:
        # Cleanup
        if os.path.exists(json_output):
            os.remove(json_output)


def append_metrics(metrics: dict, host_info: dict, revision: str) -> None:
    """Append metrics to metrics.json in JSONL format."""
    metrics_file = Path(__file__).parent.parent / "metrics" / "metrics.json"
    metrics_file.parent.mkdir(parents=True, exist_ok=True)

    # Create metric entry
    entry = {
        "host": host_info,
        "timestamp": int(time.time()),
        "revision": revision,
        "metrics": metrics,
    }

    # Append to JSONL file
    with open(metrics_file, "a") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"✅ Metrics appended to {metrics_file}")


def print_metrics_summary(metrics: dict) -> None:
    """Print a summary of collected metrics."""
    print("\n📊 Collected Metrics:")
    print("=" * 70)

    # Group by scenario
    scenarios = {}
    for key, (value, unit) in metrics.items():
        scenario = key.rsplit("/", 1)[0]
        if scenario not in scenarios:
            scenarios[scenario] = {}
        metric_name = key.rsplit("/", 1)[1]
        scenarios[scenario][metric_name] = (value, unit)

    for scenario in sorted(scenarios.keys()):
        print(f"\n{scenario}:")
        for metric, (value, unit) in scenarios[scenario].items():
            print(f"  {metric}: {value} {unit}")

    print("\n" + "=" * 70)


def main():
    """Main entry point."""
    print("🚀 Collecting performance metrics...\n")

    # Get system info
    host_info = get_system_info()
    print(f"📱 System: {host_info['os']}")
    print(f"   CPU: {host_info['cpu']}")
    print(f"   Memory: {host_info['mem']}")
    print(f"   Python: {host_info['python_version']}\n")

    # Get revision
    revision = get_git_revision()
    if revision:
        print(f"📌 Commit: {revision}\n")
    else:
        print("⚠️ Could not determine git revision\n")
        revision = "unknown"

    # Run benchmarks
    try:
        metrics = run_benchmarks()
    except Exception as e:
        print(f"❌ Failed to run benchmarks: {e}")
        return False

    if not metrics:
        print("❌ No metrics collected")
        return False

    # Print summary
    print_metrics_summary(metrics)

    # Append to metrics file
    try:
        append_metrics(metrics, host_info, revision)
    except Exception as e:
        print(f"❌ Failed to save metrics: {e}")
        return False

    print("\n✨ Metrics collection complete!")
    return True


if __name__ == "__main__":
    import sys

    success = main()
    sys.exit(0 if success else 1)
