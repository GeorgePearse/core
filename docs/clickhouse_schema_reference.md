# ClickHouse Schema Quick Reference

Complete schema reference for all 7 Genesis ClickHouse tables.

## Table of Contents
1. [llm_logs](#llm_logs) - LLM API calls
2. [agent_actions](#agent_actions) - System events
3. [evolution_runs](#evolution_runs) - Experiment runs
4. [generations](#generations) - Generation statistics
5. [individuals](#individuals) - Code variants
6. [pareto_fronts](#pareto_fronts) - Pareto frontier snapshots
7. [code_lineages](#code_lineages) - Parent-child relationships

---

## llm_logs

**Purpose:** Track every LLM API call (auto-populated)

```sql
CREATE TABLE llm_logs (
    id UUID,                    -- Unique call ID
    timestamp DateTime64(3),    -- When the call was made
    model String,               -- LLM model name
    messages String,            -- JSON array of input messages
    response String,            -- LLM response text
    cost Float64,               -- API cost in USD
    execution_time Float64,     -- Request duration in seconds
    metadata String             -- JSON with context (task, generation, etc.)
) ENGINE = MergeTree()
ORDER BY timestamp;
```

**Example Query:**
```sql
SELECT model, count(*) as calls, sum(cost) as total_cost
FROM llm_logs
WHERE timestamp > now() - INTERVAL 1 DAY
GROUP BY model;
```

---

## agent_actions

**Purpose:** Generic event logging (auto-populated)

```sql
CREATE TABLE agent_actions (
    id UUID,                    -- Unique action ID
    timestamp DateTime64(3),    -- When the action occurred
    action_type String,         -- "job_submitted", "job_completed", etc.
    details String,             -- JSON with action-specific data
    metadata String             -- JSON with additional context
) ENGINE = MergeTree()
ORDER BY timestamp;
```

**Example Query:**
```sql
SELECT action_type, count(*) as count
FROM agent_actions
WHERE timestamp > now() - INTERVAL 1 HOUR
GROUP BY action_type;
```

---

## evolution_runs

**Purpose:** Track each complete evolution experiment (1 row per run)

```sql
CREATE TABLE evolution_runs (
    run_id String,              -- Unique run identifier
    start_time DateTime64(3),   -- Run start timestamp
    end_time DateTime64(3),     -- Run completion (default: epoch 0)
    task_name String,           -- Task being evolved
    config String,              -- Full Hydra config as JSON
    status String,              -- "running" | "completed" | "failed"
    total_generations Int32,    -- Number of generations completed
    population_size Int32,      -- Population size per generation
    cluster_type String,        -- "local" | "e2b"
    database_path String        -- Path to SQLite results database
) ENGINE = MergeTree()
ORDER BY start_time;
```

**Example Query:**
```sql
SELECT run_id, task_name, status, total_generations
FROM evolution_runs
WHERE status = 'running'
ORDER BY start_time DESC;
```

---

## generations

**Purpose:** Aggregate statistics per generation

```sql
CREATE TABLE generations (
    run_id String,              -- Links to evolution_runs.run_id
    generation Int32,           -- Generation number (0 = initial)
    timestamp DateTime64(3),    -- When generation completed
    num_individuals Int32,      -- Population size
    best_score Float64,         -- Best fitness in generation
    avg_score Float64,          -- Mean fitness
    pareto_size Int32,          -- Pareto frontier size
    total_cost Float64,         -- Total API cost (USD)
    metadata String             -- JSON with additional stats
) ENGINE = MergeTree()
ORDER BY (run_id, generation);
```

**Example Query:**
```sql
SELECT generation, best_score, avg_score, total_cost
FROM generations
WHERE run_id = 'YOUR_RUN_ID'
ORDER BY generation;
```

---

## individuals

**Purpose:** Every code variant evaluated (most granular table)

```sql
CREATE TABLE individuals (
    run_id String,              -- Links to evolution_runs.run_id
    individual_id String,       -- Unique variant ID
    generation Int32,           -- Which generation
    timestamp DateTime64(3),    -- Evaluation timestamp
    parent_id String,           -- Parent ID (empty for initial)
    mutation_type String,       -- "init" | "mutate" | "crossover"
    fitness_score Float64,      -- Primary objective score
    combined_score Float64,     -- Multi-objective score
    metrics String,             -- JSON of all metrics
    is_pareto Boolean,          -- On Pareto frontier?
    api_cost Float64,           -- Cost to generate variant
    embed_cost Float64,         -- Embedding computation cost
    novelty_cost Float64,       -- Novelty scoring cost
    code_hash String,           -- SHA-256 of code
    code_size Int32             -- Code size in bytes
) ENGINE = MergeTree()
ORDER BY (run_id, generation, timestamp);
```

**Example Query:**
```sql
SELECT individual_id, generation, fitness_score, mutation_type
FROM individuals
WHERE run_id = 'YOUR_RUN_ID'
ORDER BY fitness_score DESC
LIMIT 10;
```

---

## pareto_fronts

**Purpose:** Pareto frontier snapshot per generation

```sql
CREATE TABLE pareto_fronts (
    run_id String,              -- Links to evolution_runs.run_id
    generation Int32,           -- Generation number
    timestamp DateTime64(3),    -- When computed
    individual_id String,       -- ID of Pareto member
    fitness_score Float64,      -- Primary objective
    combined_score Float64,     -- Combined score
    metrics String              -- JSON of all metrics
) ENGINE = MergeTree()
ORDER BY (run_id, generation, fitness_score);
```

**Example Query:**
```sql
SELECT generation, count(*) as pareto_size
FROM pareto_fronts
WHERE run_id = 'YOUR_RUN_ID'
GROUP BY generation
ORDER BY generation;
```

---

## code_lineages

**Purpose:** Parent-child relationships (evolutionary tree)

```sql
CREATE TABLE code_lineages (
    run_id String,              -- Links to evolution_runs.run_id
    child_id String,            -- Child individual ID
    parent_id String,           -- Parent individual ID
    generation Int32,           -- Generation child was created
    mutation_type String,       -- "init" | "mutate" | "crossover"
    timestamp DateTime64(3),    -- When relationship created
    fitness_delta Float64,      -- child_fitness - parent_fitness
    edit_summary String         -- Human-readable change description
) ENGINE = MergeTree()
ORDER BY (run_id, generation, timestamp);
```

**Example Query:**
```sql
SELECT child_id, parent_id, mutation_type, fitness_delta
FROM code_lineages
WHERE run_id = 'YOUR_RUN_ID' AND fitness_delta > 0
ORDER BY fitness_delta DESC
LIMIT 20;
```

---

## Entity Relationship Diagram

```
┌────────────────┐
│evolution_runs  │
│ run_id (PK)    │
└────────┬───────┘
         │
         ├──────┬──────────┬──────────────┬─────────────┐
         │      │          │              │             │
         ▼      ▼          ▼              ▼             ▼
    ┌────────┐┌────────┐┌────────────┐┌─────────┐┌─────────┐
    │gens    ││inds    ││pareto      ││lineages ││llm_logs │
    │        ││        ││            ││         ││         │
    └────────┘└────────┘└────────────┘└─────────┘└─────────┘
                  │          │            │
                  └──────────┴────────────┘
                       (same individuals)
```

**Foreign Key Relationships (logical, not enforced):**
- `generations.run_id` → `evolution_runs.run_id`
- `individuals.run_id` → `evolution_runs.run_id`
- `pareto_fronts.run_id` → `evolution_runs.run_id`
- `pareto_fronts.individual_id` → `individuals.individual_id`
- `code_lineages.run_id` → `evolution_runs.run_id`
- `code_lineages.child_id` → `individuals.individual_id`
- `code_lineages.parent_id` → `individuals.individual_id`

---

## Index Usage

All tables are ordered for optimal query performance:

| Table | ORDER BY | Best For |
|-------|----------|----------|
| `llm_logs` | `timestamp` | Time-range queries |
| `agent_actions` | `timestamp` | Time-range queries |
| `evolution_runs` | `start_time` | Recent runs, chronological order |
| `generations` | `(run_id, generation)` | Per-run generation lookups |
| `individuals` | `(run_id, generation, timestamp)` | Per-run/generation queries |
| `pareto_fronts` | `(run_id, generation, fitness_score)` | Pareto analysis per generation |
| `code_lineages` | `(run_id, generation, timestamp)` | Lineage tracing per run |

**Query Optimization Tips:**
- Always filter by `run_id` when querying evolution tables
- Use `timestamp` ranges for log tables
- Specify only needed columns (avoid `SELECT *`)
- Use `PREWHERE` for cheap filters before expensive ones

---

## Data Types

- **UUID** - 16-byte unique identifier
- **DateTime64(3)** - Timestamp with millisecond precision
- **String** - Variable-length string (UTF-8)
- **Int32** - 32-bit signed integer
- **Float64** - 64-bit floating point
- **Boolean** - True/false (stored as UInt8)

JSON fields (`messages`, `response`, `details`, `metadata`, `config`, `metrics`):
- Stored as String
- Query with `JSONExtract*` functions:
  ```sql
  SELECT JSONExtractFloat(metrics, 'accuracy') as accuracy
  FROM individuals;
  ```

---

## Full Schema DDL

Copy-paste to recreate all tables:

```sql
-- LLM Logs
CREATE TABLE llm_logs (
    id UUID, timestamp DateTime64(3), model String, messages String,
    response String, cost Float64, execution_time Float64, metadata String
) ENGINE = MergeTree() ORDER BY timestamp;

-- Agent Actions
CREATE TABLE agent_actions (
    id UUID, timestamp DateTime64(3), action_type String,
    details String, metadata String
) ENGINE = MergeTree() ORDER BY timestamp;

-- Evolution Runs
CREATE TABLE evolution_runs (
    run_id String, start_time DateTime64(3), end_time DateTime64(3),
    task_name String, config String, status String, total_generations Int32,
    population_size Int32, cluster_type String, database_path String
) ENGINE = MergeTree() ORDER BY start_time;

-- Generations
CREATE TABLE generations (
    run_id String, generation Int32, timestamp DateTime64(3),
    num_individuals Int32, best_score Float64, avg_score Float64,
    pareto_size Int32, total_cost Float64, metadata String
) ENGINE = MergeTree() ORDER BY (run_id, generation);

-- Individuals
CREATE TABLE individuals (
    run_id String, individual_id String, generation Int32,
    timestamp DateTime64(3), parent_id String, mutation_type String,
    fitness_score Float64, combined_score Float64, metrics String,
    is_pareto Boolean, api_cost Float64, embed_cost Float64,
    novelty_cost Float64, code_hash String, code_size Int32
) ENGINE = MergeTree() ORDER BY (run_id, generation, timestamp);

-- Pareto Fronts
CREATE TABLE pareto_fronts (
    run_id String, generation Int32, timestamp DateTime64(3),
    individual_id String, fitness_score Float64, combined_score Float64,
    metrics String
) ENGINE = MergeTree() ORDER BY (run_id, generation, fitness_score);

-- Code Lineages
CREATE TABLE code_lineages (
    run_id String, child_id String, parent_id String, generation Int32,
    mutation_type String, timestamp DateTime64(3), fitness_delta Float64,
    edit_summary String
) ENGINE = MergeTree() ORDER BY (run_id, generation, timestamp);
```
