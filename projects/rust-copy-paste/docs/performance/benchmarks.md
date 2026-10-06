# Benchmarks

The Copy-Paste augmentation includes comprehensive performance benchmarks to track and optimize performance across releases.

## Running Benchmarks

### Install Dependencies

```bash
uv pip install -e ".[benchmarks]"
```

### Run All Benchmarks

```bash
python benchmarks/collect_metrics.py
```

This will:
1. Generate test data
2. Run benchmarks for all scenarios
3. Collect system metrics
4. Store results in `metrics/metrics.json`
5. Display a summary report

### Run Specific Benchmarks

```bash
# Run only baseline tests
pytest benchmarks/benchmark_copy_paste.py::TestCopyPasteBenchmarks::test_transform -k "baseline_512x512_1obj" -v

# Run with specific options
pytest benchmarks/benchmark_copy_paste.py -v --benchmark-warmup=on --benchmark-disable-gc

# Save raw benchmark data
pytest benchmarks/benchmark_copy_paste.py --benchmark-json=results.json
```

## Benchmark Scenarios

The benchmarking suite tests multiple scenarios to cover different use cases:

| Scenario | Configuration | Typical Time | Typical Throughput |
|----------|---------------|--------------|-------------------|
| baseline_512x512_1obj | 512×512 image, 1 object | 20-25 ms | 40-50 img/s |
| baseline_512x512_3obj | 512×512 image, 3 objects | 25-35 ms | 30-40 img/s |
| large_1024x1024_1obj | 1024×1024 pixels | 50-65 ms | 15-20 img/s |
| large_2048x2048_1obj | 2048×2048 pixels | 80-125 ms | 8-12 img/s |
| multi_object_5obj | 512×512 image, 5 objects | 40-60 ms | 15-25 img/s |
| multi_object_10obj | 512×512 image, 10 objects | 125-200 ms | 5-8 img/s |
| with_rotation | With random rotation | +10-15% overhead | |
| with_scaling | With random scaling | +5-10% overhead | |
| random_background | Background generation | +20-30% overhead | |
| xray_blending | X-ray blend mode | +10-20% overhead | |

## Version 1.x Performance Improvements

Version 1.x includes several significant performance optimizations while maintaining thread-safety:

### Bounding Box Calculation Optimization

**4x faster bbox extraction** through single-pass calculation:

| Version | Method | Performance |
|---------|--------|-------------|
| v0.x | Four-pass (min_x, max_x, min_y, max_y separately) | ~400μs for 100 objects |
| v1.x | Single-pass (all bounds simultaneously) | ~100μs for 100 objects |

**Implementation**: Optimized loop calculates all four bounds in one iteration.

### DoS Prevention

Added maximum iteration limits to flood fill operations:

- **Max iterations**: 1,000,000 per flood fill
- **Protection**: Prevents infinite loops on malformed masks
- **Performance impact**: <1% overhead for normal cases
- **Security benefit**: Prevents denial-of-service attacks

### Lazy Loading Optimization

The system now performs **Lazy Patch Extraction**, deferring heavy memory allocation until after object selection.

- **Impact**: Reduces memory spikes by 40-60% in scenes with many candidate objects.
- **Benefit**: Allows processing high-density masks (e.g., 100+ objects) without OOM errors, as only the few pasted objects are ever extracted.

### Thread-Safety Overhead

Arc<Mutex> adds minimal overhead compared to RefCell:

| Operation | RefCell (v0.x) | Arc<Mutex> (v1.x) | Overhead |
|-----------|----------------|-------------------|----------|
| Lock/unlock | N/A | ~50-100ns | Negligible |
| Apply transform | 20ms | 20.05ms | <0.3% |
| Bbox generation | 100μs | 100.2μs | <0.2% |

**Conclusion**: Thread-safety comes at virtually no performance cost.

### Multi-Worker DataLoader Performance

Thread-safe design enables near-linear scaling with multiple workers:

| Workers | Throughput (512×512, 1 obj) | Speedup | Efficiency |
|---------|----------------------------|---------|------------|
| 1 | 45 img/s | 1.0x | 100% |
| 2 | 85 img/s | 1.9x | 95% |
| 4 | 170 img/s | 3.8x | 95% |
| 8 | 320 img/s | 7.1x | 89% |

**Test Configuration**:
- Image size: 512×512 pixels
- Objects pasted: 1 per image
- Hardware: 8-core CPU
- Batch size: 32

**Scaling Analysis**:
- Near-linear speedup up to 4 workers
- Slight efficiency drop with 8+ workers due to context switching
- No lock contention (each worker has separate transform instance)

### Input Validation Performance

Comprehensive validation adds minimal overhead:

| Validation Step | Time | Impact |
|----------------|------|--------|
| Dimension checks | ~50ns | <0.001% |
| Channel count validation | ~30ns | <0.001% |
| Shape matching | ~100ns | <0.001% |
| Total validation | ~500ns | <0.003% |

**Benefit**: Early validation prevents crashes and provides clear error messages with negligible cost.

## Performance Tips

### Optimize for Production

1. **Use Release Build**: Always use `cargo build --release`
2. **Multi-Worker DataLoader**: Use 4-8 workers for maximum throughput
3. **Batch Processing**: Process multiple images in batches for better efficiency
4. **Image Size**: Smaller images are faster; consider downsampling if possible
5. **Object Count**: Fewer objects paste faster; adjust `max_paste_objects`
6. **Persistent Workers**: Use `persistent_workers=True` in DataLoader to avoid respawning overhead

### Performance Comparison

Compare performance across different configurations:

```bash
# Baseline
pytest benchmarks/benchmark_copy_paste.py -v

# After optimization
pytest benchmarks/benchmark_copy_paste.py -v --benchmark-json=optimized.json

# Compare results
pytest benchmarks/benchmark_copy_paste.py --benchmark-compare=optimized.json
```

## Understanding Results

### Key Metrics

- **mean**: Average processing time
- **stddev**: Standard deviation (consistency)
- **min/max**: Minimum and maximum times observed
- **throughput**: Images processed per second

### Performance Expectations

Typical performance on modern hardware:

```
512×512, 1 object:    20-25 ms (~45 img/s)
1024×1024, 1 object:  50-65 ms (~15 img/s)
2048×2048, 1 object:  80-125 ms (~10 img/s)
```

Performance scales linearly with:
- Image dimensions (O(W×H))
- Number of objects (O(n))

## Continuous Benchmarking

Benchmarks are automatically run on every commit to `master`:

1. GitHub Actions workflow executes benchmarks
2. Results are stored in `metrics/metrics.json`
3. Dashboard visualizes trends over time
4. Regressions are detected automatically

See [Metrics Dashboard](metrics.md) for live performance data.

## Troubleshooting

### Inconsistent Results
- Close other applications
- Disable dynamic CPU scaling
- Run benchmarks multiple times
- Check system load: `top` or `htop`

### Slow Performance
- Verify release build: `cargo build --release`
- Check CPU usage during benchmarks
- Profile with: `perf stat python benchmarks/collect_metrics.py`
- Compare against baseline metrics

### Missing Data
- Ensure pytest-benchmark is installed
- Check for errors in benchmark runs
- Verify write access to `metrics/` directory
