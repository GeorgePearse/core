# Genesis Rust Backend

This directory contains a Rust-native backend layout that mirrors the Python backend structure under `genesis/`.

## Scope

This implementation provides:
- `core` module parity (`runner`, `sampler`, `alma_memory`, `gepa_optimizer`, `summarizer`, `novelty_judge`)
- shared data model equivalents (`Program`, `RunningJob`, `EvolutionConfig`)
- backend interfaces and implementations for:
  - `database`
    - `InMemoryProgramDatabase`
    - `ClickHouseProgramDatabase` (real adapter via HTTP SQL)
  - `llm`
    - `MockLlmClient`
    - `OpenAiClient` (real adapter via Chat Completions API)
  - `launch`
    - `MockScheduler`
    - `LocalCommandScheduler` (executes local evaluator command)
- a runnable binary (`src/main.rs`) that loads YAML config and starts the runner.

## Backend Selection

`EvolutionConfig` supports backend routing:
- `db_backend`: `in_memory` or `clickhouse`
- `llm_backend`: `mock` or `openai`
- `scheduler_backend`: `mock` or `local_command`

Environment fallbacks:
- `OPENAI_API_KEY`
- `CLICKHOUSE_URL`
- `CLICKHOUSE_USER`
- `CLICKHOUSE_PASSWORD`
- `CLICKHOUSE_DB`

## Example Config

```yaml
evo_config:
  db_backend: clickhouse
  clickhouse_url: http://localhost:8123
  clickhouse_database: default

  llm_backend: openai
  openai_model: gpt-4.1-mini
  openai_base_url: https://api.openai.com

  scheduler_backend: local_command
  eval_command: "python genesis/eval_hydra.py evaluate_function.program_path=$GENESIS_CODE_PATH"
```

## Run

```bash
cd genesis_rust_backend
cargo run -- --config ../configs/evolution/small_budget.yaml
```

If no config is supplied, defaults are used.
