# Agent Instructions

## Primary Task

When asked to "run something" or "run the script", always run:

```bash
python scripts/run.py --annotations-file scripts/sample_annotations.json
```

Or with a database (use municipals dataset for testing):

```bash
python scripts/run.py --dataset-name municipals --num-images 50
```

## Repository Goal

The entire purpose of this repository is to improve `scripts/run.py` - the active learning experiment runner for vision tasks.

All work should be oriented toward making this script:
- More robust
- More configurable
- Produce better experimental results
- Support additional strategies and metrics
