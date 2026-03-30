# Plan: Workflow Orchestration with Prefect

## Motivation

Genesis currently launches evolution experiments via CLI (`genesis_launch`) and schedules individual evaluation jobs through a custom `JobScheduler` backed by local processes or E2B cloud sandboxes. This works well for single experiments but has limitations:

- **No central visibility** -- there is no dashboard showing running, queued, or historical experiments across the team.
- **No retry / failure handling** -- if a generation crashes mid-run the entire experiment is lost; there is no automatic retry or checkpointing at the orchestration layer.
- **No cross-experiment coordination** -- running nightly benchmarks, chaining experiments (e.g. "evolve, then evaluate on hold-out, then archive"), or gating on resource availability requires manual scripting.
- **No scheduling** -- periodic tasks like nightly evolution sweeps, benchmark reruns, or database compaction must be set up outside the repo (cron, GitHub Actions).

A workflow orchestration layer (Prefect) would solve all of the above while staying Python-native and aligning with the existing codebase.

## Why Prefect

| Criterion | Prefect | Alternatives considered |
|-----------|---------|------------------------|
| Python-native | Yes -- flows and tasks are decorated functions | Airflow (heavyweight, DAG-file based), Temporal (Go SDK primary) |
| Self-hosted option | Prefect server runs in a single container | Airflow needs scheduler + webserver + metadata DB |
| Cloud option | Prefect Cloud free tier sufficient for small teams | Airflow managed (MWAA) is expensive |
| Dynamic workflows | First-class -- tasks can be created at runtime | Airflow DAGs are static at parse time |
| Retries & caching | Built-in per-task retries, result caching, timeouts | Manual in Airflow |
| Observability | Built-in UI with logs, state timeline, artifacts | Airflow UI less granular |
| Lightweight | `pip install prefect` -- single dependency | Airflow pulls in ~100+ transitive deps |

Prefect's model of decorated Python functions (`@flow`, `@task`) maps directly onto the existing Genesis code with minimal refactoring.

## Integration Points

### 1. Evolution runs as Prefect flows

The main integration wraps `EvolutionRunner.run()` in a Prefect flow:

```python
from prefect import flow, task

@task(retries=2, retry_delay_seconds=30)
def run_generation(runner, generation: int):
    """Execute a single generation of the evolution loop."""
    ...

@flow(name="genesis-evolution", log_prints=True)
def evolution_flow(variant: str, overrides: list[str] | None = None):
    """Full evolution experiment as an observable Prefect flow."""
    # Load Hydra config, build EvolutionRunner
    # Loop over generations, each as a task
    ...
```

Each generation becomes a discrete Prefect task with its own retry policy, timeout, and log stream. If generation N fails, Prefect retries it without restarting from generation 0.

### 2. Job scheduling inside generations

The existing `JobScheduler` (local / E2B) continues to own the actual process execution. Prefect sits one layer above:

```
Prefect flow (evolution_flow)
  -> Prefect task (run_generation)
       -> JobScheduler.run() [local / E2B]  # unchanged
```

This means no changes to the low-level launch code. Prefect adds observability and retry semantics on top.

### 3. Scheduled / periodic experiments

Prefect deployments allow cron-style scheduling:

```python
from prefect.deployments import Deployment

Deployment.build_from_flow(
    flow=evolution_flow,
    name="nightly-circle-packing",
    schedule={"cron": "0 2 * * *"},  # 2 AM daily
    parameters={"variant": "circle_packing_example"},
)
```

Use cases:
- **Nightly evolution sweeps** across a matrix of tasks / LLM models.
- **Periodic benchmark reruns** to detect performance regressions.
- **Database compaction / archival** on a weekly schedule.

### 4. Multi-step pipelines

Chain dependent workflows:

```python
@flow(name="evolve-and-evaluate")
def evolve_and_evaluate(variant: str):
    best_program = evolution_flow(variant)
    holdout_score = evaluate_holdout(best_program)
    if holdout_score > threshold:
        archive_to_registry(best_program)
```

### 5. Observability integration

- Prefect UI provides real-time flow run state, task-level logs, duration tracking.
- Prefect artifacts can store per-generation fitness plots alongside the flow run.
- Existing ClickHouse logging continues in parallel -- Prefect does not replace it, it layers above.

## Proposed File Structure

```
lib/python/genesis/
  orchestration/
    __init__.py
    flows.py           # @flow definitions (evolution, benchmark, pipeline)
    tasks.py           # @task wrappers around existing runner / scheduler calls
    schedules.py       # Deployment / schedule definitions
    config.py          # Prefect-specific config (server URL, work pool, etc.)
```

## Migration Path

### Phase 1: Wrap existing runner (low risk)

- Add `prefect` to optional dependencies: `pip install genesis[orchestration]`.
- Create `flows.py` wrapping `EvolutionRunner.run()` as a single-task flow.
- The existing `genesis_launch` CLI continues to work unchanged.
- New `genesis_orchestrate` entrypoint launches via Prefect.
- **No changes** to `runner.py`, `scheduler.py`, or any existing code.

### Phase 2: Per-generation tasks (medium risk)

- Refactor the generation loop inside `EvolutionRunner.run()` so each generation is callable independently.
- Wrap each generation as a Prefect task with retries.
- Add checkpointing: save population state between generations so retries resume from last good state.

### Phase 3: Schedules and pipelines (low risk)

- Define deployments for nightly sweeps, benchmarks, archival.
- Build multi-step flows (evolve -> evaluate -> archive).
- Optionally connect to Prefect Cloud for hosted scheduling and alerting.

### Phase 4: Work pools and infrastructure (medium risk)

- Configure Prefect work pools for different compute tiers (local dev, GCE, E2B).
- Map Genesis `job_type` (local / e2b) to Prefect infrastructure blocks.
- Enable launching experiments from the Prefect UI with parameter forms.

## Dependency Impact

```toml
# pyproject.toml addition (optional extra)
[project.optional-dependencies]
orchestration = ["prefect>=3.0"]
```

Prefect 3.x is the current major version and has a lighter footprint than 2.x. It is the only new dependency; it does not conflict with any existing Genesis dependencies.

## Open Questions

1. **Prefect server vs Cloud** -- self-host on the existing GCE Plane instance, or use Prefect Cloud free tier?
2. **Granularity** -- should individual candidate evaluations (within a generation) also be Prefect tasks, or keep that inside `JobScheduler`?
3. **ClickHouse overlap** -- Prefect stores its own run metadata. Decide whether to deduplicate with the existing ClickHouse logger or keep both.
4. **Hydra compatibility** -- Prefect has its own config injection. Need to ensure Hydra `@hydra.main` and Prefect `@flow` compose cleanly (they do when Hydra runs inside the flow function).
