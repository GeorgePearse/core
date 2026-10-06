# Vision Agents

## Goal

The primary goal of this repository is to improve `scripts/run.py` - the active learning experiment runner.

## Running the Main Script

```bash
# With local annotations file
python scripts/run.py --annotations-file scripts/sample_annotations.json --budgets 0,5,10,20,50

# With database connection (use municipals dataset for testing)
python scripts/run.py --dataset-name municipals --num-images 50 --budgets 0,5,10,20,50
```

## Key Arguments

- `--dataset-name` or `--annotations-file` (required, mutually exclusive)
- `--num-images` - number of images to process (default: 50)
- `--budgets` - comma-separated annotation budgets (default: 0,5,10,20,50)
- `--strategies` - sampling strategies: uncertainty, random, diversity, threshold
- `--output-dir` - results directory (default: ./experiment_results)
- `--verbose` - enable debug logging

## Git Workflow

- Always commit and push directly to `main`. No branches or PRs needed for this repo.
- Commit and push after every change without waiting to be asked.

## Environment

- Requires `.env` file with `PG_DATABASE_URL` for database mode
- Requires `GEMINI_API_KEY` for VLM inference
- Uses virtual environment at `.venv/`
