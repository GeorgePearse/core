# Performance Metrics Dashboard

Real-time performance metrics are automatically collected and visualized on our [metrics dashboard](https://georgepearse.github.io/rust-copy-paste/).

## Overview

Performance metrics are automatically collected on every push to the `master` branch using GitHub Actions. Results are stored in JSONL format and displayed on the interactive metrics dashboard.

## How It Works

### Automated Collection

Every commit to master triggers:

```
GitHub Push → GitHub Actions → pytest-benchmark → collect_metrics.py → metrics/metrics.json → Dashboard
```

### Data Format (JSONL)

Each line in `metrics/metrics.json` is a complete JSON object containing:

```json
{
  "host": {
    "os": "Linux-5.10.0-36-cloud-amd64-x86_64",
    "cpu": "AMD EPYC 7763 64-Core Processor",
    "mem": "16.0 GB",
    "python_version": "3.10.12"
  },
  "timestamp": 1730304000,
  "revision": "8d5ffdc",
  "metrics": {
    "baseline_512x512_1obj/time_ms": [22.5, "ms"],
    "baseline_512x512_1obj/throughput": [44.4, "img/s"],
    "baseline_512x512_1obj/max_ms": [28.3, "ms"]
  }
}
```

## Dashboard Features

The metrics dashboard provides:

### Charts

1. **Processing Time Trend** - Median processing time over commits
2. **Throughput Trend** - Images per second over time
3. **Performance Comparison** - Latest results by scenario
4. **Maximum Time (P100 Latency)** - Latency trends over time

### Interactive Controls

- **Normalize to first value**: View relative performance changes
- **Download Metrics**: Export raw JSONL data
- **Scenario filter**: Show/hide specific test scenarios
- **Hover tooltips**: Exact values for any data point

## Running Benchmarks Locally

### Install Benchmark Dependencies

```bash
uv pip install -e ".[benchmarks]"
```

### Collect Metrics Manually

```bash
python benchmarks/collect_metrics.py
```

This will:
1. Generate/use the dummy dataset
2. Run pytest-benchmark on all scenarios
3. Collect system metrics (OS, CPU, memory)
4. Append results to `metrics/metrics.json`
5. Display a summary

### Run Specific Benchmarks

```bash
# Run only baseline tests
pytest benchmarks/benchmark_copy_paste.py::TestCopyPasteBenchmarks::test_transform[baseline_512x512_1obj] -v

# Run with warmup and disable garbage collection
pytest benchmarks/benchmark_copy_paste.py -v --benchmark-warmup=on --benchmark-disable-gc

# Save raw benchmark data
pytest benchmarks/benchmark_copy_paste.py --benchmark-json=results.json
```

## Performance Expectations

Based on typical hardware:

| Scenario | Expected Throughput | Expected Time |
|----------|-------------------|--------------|
| Baseline (512×512, 1 obj) | 40-50 img/s | 20-25 ms |
| Large (2048×2048, 1 obj) | 8-12 img/s | 80-125 ms |
| Heavy (512×512, 10 obj) | 5-8 img/s | 125-200 ms |

**Note:** Actual performance depends on:
- Hardware (CPU cores, RAM, disk speed)
- System load during benchmark run
- Python/library versions
- Caching effectiveness

## Regression Detection

To identify performance regressions:

1. Compare latest metrics against baseline
2. Look for >5-10% drops in throughput
3. Check for increases in processing time
4. Review recent commits for potential causes

Example:
```
Baseline throughput: 48.1 img/s
Latest throughput: 45.2 img/s
Regression: 5.9%
```

## Customizing Benchmarks

### Add a New Scenario

Edit `benchmarks/scenarios.py`:

```python
SCENARIOS = {
    "my_scenario": BenchmarkConfig(
        name="My Custom Scenario",
        image_width=512,
        image_height=512,
        max_paste_objects=2,
        use_rotation=True,
    )
}
```

Benchmarks will automatically run for the new scenario.

### Modify Collection Script

Edit `benchmarks/collect_metrics.py` to:
- Change benchmark parameters
- Add custom metric collection
- Modify system info captured

## GitHub Actions Workflow

Location: `.github/workflows/benchmarks.yml`

**Triggers:**
- Push to `master` branch
- Weekly schedule (Sundays at midnight UTC)

**Workflow Steps:**
1. Checkout code with full git history
2. Setup Python + uv
3. Install dependencies including `[benchmarks]` extras
4. Generate dummy dataset
5. Run `collect_metrics.py`
6. Commit and push metrics to repository
7. Upload metrics as GitHub artifact
8. Generate workflow summary

## Best Practices

1. **Monitor regularly**: Check dashboard weekly for trends
2. **Investigate regressions**: >5-10% drops warrant investigation
3. **Document changes**: Note infrastructure/library updates that affect metrics
4. **Compare fairly**: Use similar hardware/conditions for comparison
5. **Focus on trends**: Look at long-term trends, not individual spikes

## Troubleshooting

### Metrics Not Updating

1. Check workflow run: GitHub → Actions → Performance Benchmarks
2. Review error logs in workflow steps
3. Verify `metrics/metrics.json` file exists
4. Ensure GitHub Pages is enabled (Settings → Pages)

### Missing Data Points

- New commits may not have metrics (workflow in progress)
- Failed benchmarks are skipped
- Check workflow artifacts for details

### Dashboard Not Loading

1. Clear browser cache
2. Check browser console for errors
3. Verify `metrics/metrics.json` file is readable
4. Ensure GitHub Pages is configured

## See Also

- [Benchmarks Guide](benchmarks.md) - Running and understanding benchmarks
- [Building from Source](../development/building.md) - Build instructions
- [Metrics Data](https://raw.githubusercontent.com/GeorgePearse/rust-copy-paste/master/metrics/metrics.json) - Raw JSONL data
