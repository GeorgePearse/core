# ModelMode

An MCP server that lets a supervising agent turn examples into small, reusable
classifiers. Register a dataset, launch a bounded search, review validation errors,
open the final test once, then publish a versioned capability and call `predict`.

The first backend is real supervised learning: full-weight BERT-tiny, BERT-mini and
ELECTRA-small fine-tuning, plus TF-IDF and numeric sklearn baselines. Modal runs
training on one shared T4 worker. Published fine-tuned models run locally on CPU
without a network connection. No hosted LLM calls are made by this package.

## Install

From this directory, with Python 3.12 or newer:

```sh
uv venv
uv pip install -e '.[train,modal,dev]'
modal setup
modal deploy -m modelmode.modal_app
modelmode-mcp --root ~/.local/share/modelmode
```

`modal` and `modelmode-mcp` must be on PATH (activate `.venv` or use its full path).
The deployment creates `modelmode-hf-cache` and `modelmode-artifacts` volumes.
It scales to zero, has no automatic retry, and is capped at one T4 GPU. Modal
training incurs cloud charges. The caller's whole-job deadline includes queueing,
startup, downloads and training; the remote function also has a one-hour ceiling.

For local baselines only, install `.[dev]`. Optional `.[static]` adds Model2Vec and
`.[transformers]` adds frozen MiniLM embeddings with a trained logistic head.

## Python

```python
from modelmode import Workspace

workspace = Workspace("./.modelmode")
dataset = workspace.create_dataset("intents", rows)  # see schema below
run = workspace.learn(
    dataset["dataset_id"],
    candidates=["tfidf_word", "bert_tiny", "bert_mini"],
    execution="modal", budget_seconds=900,
    training={"epochs": 4, "learning_rate": 3e-4, "max_length": 96},
)
run = workspace.wait(run["run_id"])
workspace.review(run["run_id"])
workspace.evaluate(run["run_id"])  # final test: no more tuning on this dataset
workspace.publish(run["run_id"], "intent_router", abstain_below=0.8)
workspace.predict("intent_router", ["Where is my card?"], version=1)
```

Each row has `id`, `label`, and either `text` or numeric `features`. Optional fields:
`group`, `split` (`train`, `validation`, `test`), `label_source` (`provided`, `human`,
`teacher`). Set all splits or none; automatic splitting is grouped 60/20/20.
Duplicate normalized inputs and transitive user groups cannot cross partitions.
All classes must occur in all three partitions. Teacher labels are training-only;
label provenance is supplied by the caller, not independently certified.

For a random-weight control set `training={"initialization": "random"}`. This
trains a randomly initialized encoder with the pretrained tokenizer, not a new
language model pretrained from scratch. All encoder weights are updated in both
modes. Hyperparameters, checkpoint revision, parameter counts, per-epoch losses,
pure training time, loading time and end-to-end time are persisted.

## MCP and CLI

Configure your MCP host to launch the installed `modelmode-mcp` executable with
`["--root", "/absolute/trusted/workspace"]`. It exposes `catalog`, `create_dataset`,
`list_datasets`, `learn`, `get_run`, `list_runs`, `cancel`, `review`, `evaluate`,
`publish`, `list_capabilities`, and `predict`. The frontier host supplies task
judgment, examples and failure review; the server supplies bounded computation.

```sh
modelmode --root ./.modelmode catalog
modelmode --root ./.modelmode get_run --json '{"run_id":"..."}'
```

Choose `objective="fastest_at_quality"` with a positive `min_score` to select the
lowest measured warm CPU cost among candidates meeting the validation floor.
Otherwise selection maximizes the requested validation metric. Timing includes
encoding, excludes loading, and is amortized over a batch: it is not request
latency. Fine-tuning always measures inference on CPU after moving weights off GPU.

## Evaluation and operational boundaries

- Final test evaluation seals the dataset ID against further searches. It tests
  only the selected model and dummy baseline. Publication requires beating that
  baseline and meeting the configured floor on both validation and test.
- This is a workflow guard, not protection against a user making a fresh dataset
  with the same test cohort. Freeze genuinely independent evaluation data.
- Modal receives no test rows. Remote receipts live on the artifacts volume;
  returned artifact hashes are checked before local publication. Weights and
  tokenizer are embedded in fine-tuned artifacts; frozen-encoder artifacts instead
  reference an upstream pinned revision and need its separate cached files.
- `cancel` and timeout cancel the actual Modal FunctionCall, including its
  container. A local host crash can leave a call running up to its remote ceiling;
  its call ID is saved in `state.json` for explicit cancellation/recovery in Modal.
- One job is active per local workspace and one GPU container per deployed app.
  Before submission, task occupancy is recorded and 40 active tasks blocks work.
  Multi-GPU containers need a separate GPU inventory: task count alone cannot
  enforce an organization-wide GPU reserve.
- Artifacts use joblib. Only use a trusted workspace; never import third-party
  pickles. Probabilities are not calibrated confidence. Abstention routes work to
  the supervising agent but does not certify correctness.

Run tests with `pytest`; lint with `ruff check .` and `ruff format --check .`.

## Measured example

See the [BANKING77 pilot](docs/benchmark-20261011.md) and its
[interactive report](https://storage.googleapis.com/binit-public/modelmode/20261011/report.html).
Reproduce with `python examples/banking77.py --root /tmp/modelmode-banking` after
deploying the Modal worker. The default comparison includes pretrained tiny/mini,
a random-weight tiny control, and both TF-IDF baselines. The final test is opened
automatically when the search succeeds; `--no-final-test` leaves it closed.

Source is baked into the Modal image. Redeploy after updating this package: the
worker checks the caller's implementation hash before training and result import
checks it again. This avoids silently reusing a worker with an older implementation.
