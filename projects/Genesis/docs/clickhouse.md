# ClickHouse Integration

Genesis includes comprehensive ClickHouse integration for tracking evolution runs, LLM interactions, and system events in real-time. All data is automatically logged to ClickHouse for analysis, visualization, and debugging.

## Quick Overview

**7 Tables** tracking different aspects of evolution:

| Table | Purpose | Row Count (typical) |
|-------|---------|---------------------|
| `evolution_runs` | Each experiment run | 1 per run |
| `generations` | Per-generation stats | 10-100 per run |
| `individuals` | Every code variant | 100-1000s per run |
| `pareto_fronts` | Pareto frontier snapshots | 3-20 per generation |
| `code_lineages` | Parent-child relationships | Same as individuals |
| `llm_logs` | Every LLM API call | 1000s per run |
| `agent_actions` | System events | 100s per run |

## Setup

1. **Set Environment Variable:**
   ```bash
   export CLICKHOUSE_URL="https://user:password@host:port/database"
   ```
   Or add to your `.env` file.

2. **Install Client:**
   ```bash
   uv pip install clickhouse-connect
   ```

3. **Verify Connection:**
   ```bash
   python scripts/test_clickhouse.py
   ```
   
   You should see:
   ```
   ✅ ClickHouse connection successful!
   Connected to database: default
   
   📊 Tables: evolution_runs, generations, individuals, pareto_fronts, code_lineages, llm_logs, agent_actions
   ```

## Tables

Genesis uses 7 ClickHouse tables to track everything from LLM API calls to evolutionary lineages. Tables are automatically created on first connection.

---

### Core Logging Tables

These tables capture system-level events and LLM interactions.

#### `llm_logs`
**Purpose:** Track every LLM API call made during evolution, including prompts, responses, costs, and timing.

**Use Cases:**
- Debug prompt quality and LLM responses
- Analyze API costs per model
- Identify slow LLM calls
- Audit what the system asked and received

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Unique identifier for this LLM call |
| `timestamp` | DateTime64(3) | Millisecond precision timestamp when call was made |
| `model` | String | LLM model name (e.g., "claude-3-5-sonnet-20241022", "gpt-4") |
| `messages` | String | JSON-encoded array of messages sent to LLM. Format: `[{"role": "user", "content": "..."}]` |
| `response` | String | Full text response from the LLM |
| `cost` | Float64 | API cost in USD for this call (calculated from token usage) |
| `execution_time` | Float64 | Time in seconds from request to response |
| `metadata` | String | JSON with additional context: task name, generation number, mutation type, etc. |

**Example Row:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2024-01-15 14:23:45.123",
  "model": "claude-3-5-sonnet-20241022",
  "messages": "[{\"role\":\"user\",\"content\":\"Improve this code...\"}]",
  "response": "Here's an improved version...",
  "cost": 0.0234,
  "execution_time": 2.456,
  "metadata": "{\"task\":\"circle_packing\",\"generation\":5}"
}
```

---

#### `agent_actions`
**Purpose:** Generic event logging for system actions (job submissions, completions, errors, etc.)

**Use Cases:**
- Track job queue state over time
- Debug job failures
- Monitor system throughput
- Analyze which actions are most common

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Unique identifier for this action |
| `timestamp` | DateTime64(3) | When the action occurred |
| `action_type` | String | Type of action: "job_submitted", "job_completed", "job_failed", "archive_updated", etc. |
| `details` | String | JSON with action-specific data (job_id, generation, parent_id, scores, etc.) |
| `metadata` | String | JSON with additional context (configuration, environment info, etc.) |

**Example Row (job submission):**
```json
{
  "id": "650e8400-e29b-41d4-a716-446655440001",
  "timestamp": "2024-01-15 14:23:45.500",
  "action_type": "job_submitted",
  "details": "{\"job_id\":\"job_123\",\"generation\":5,\"parent_id\":\"ind_42\",\"exec_fname\":\"code_gen5_123.py\"}",
  "metadata": "{\"cluster\":\"local\",\"task\":\"circle_packing\"}"
}
```

**Example Row (job completion):**
```json
{
  "action_type": "job_completed",
  "details": "{\"job_id\":\"job_123\",\"generation\":5,\"correct\":true,\"combined_score\":0.95,\"api_costs\":0.05}",
  "metadata": "{\"public_metrics\":{\"fitness\":0.95,\"size\":1024}}"
}
```

---

### Evolution Tracking Tables

These tables capture the evolutionary process: runs, generations, individuals, and their relationships.

#### `evolution_runs`
**Purpose:** High-level tracking of each complete evolutionary experiment. One row per `genesis_launch` invocation.

**Use Cases:**
- List all experiments ever run
- Compare configurations across runs
- Track which runs are still running vs completed
- Find the database file for a specific run

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `run_id` | String | Unique identifier for this evolution run (e.g., timestamp-based ID or UUID) |
| `start_time` | DateTime64(3) | When the evolution run started |
| `end_time` | DateTime64(3) | When the run completed (defaults to epoch 0 until completion) |
| `task_name` | String | Name of the task being evolved (e.g., "circle_packing", "mask_to_seg") |
| `config` | String | Full Hydra configuration as JSON (evolution params, LLM settings, etc.) |
| `status` | String | Current status: "running", "completed", "failed" |
| `total_generations` | Int32 | Total number of generations completed (0 until run finishes) |
| `population_size` | Int32 | Population size per generation (from config) |
| `cluster_type` | String | Execution environment: "local" or "e2b" |
| `database_path` | String | Path to the SQLite database file storing results |

**Example Row:**
```json
{
  "run_id": "run_20240115_142345",
  "start_time": "2024-01-15 14:23:45.000",
  "end_time": "2024-01-15 16:45:12.000",
  "task_name": "circle_packing",
  "config": "{\"evolution\":{\"num_generations\":10,\"pop_size\":20},\"llm\":{\"model\":\"claude-3-5-sonnet\"}}",
  "status": "completed",
  "total_generations": 10,
  "population_size": 20,
  "cluster_type": "local",
  "database_path": "/path/to/results/circle_packing_20240115.db"
}
```

**Key Queries:**
```sql
-- Active runs
SELECT run_id, task_name, start_time, total_generations
FROM evolution_runs 
WHERE status = 'running';

-- Compare configurations
SELECT run_id, task_name, config
FROM evolution_runs
WHERE task_name = 'circle_packing'
ORDER BY start_time DESC;
```

---

#### `generations`
**Purpose:** Track aggregate statistics for each generation within an evolution run.

**Use Cases:**
- Plot fitness improvement over time
- Identify stagnant generations (no improvement)
- Track API cost burn rate per generation
- Monitor Pareto frontier growth

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `run_id` | String | Links to `evolution_runs.run_id` |
| `generation` | Int32 | Generation number (0 = initial population, 1+ = evolved) |
| `timestamp` | DateTime64(3) | When this generation completed evaluation |
| `num_individuals` | Int32 | How many individuals were evaluated in this generation |
| `best_score` | Float64 | Highest fitness score achieved in this generation |
| `avg_score` | Float64 | Mean fitness score across all individuals |
| `pareto_size` | Int32 | Number of individuals on the Pareto frontier (for multi-objective) |
| `total_cost` | Float64 | Total API cost (USD) spent on this generation (LLM + embeddings + novelty) |
| `metadata` | String | JSON with additional stats: median score, std dev, elite count, etc. |

**Example Row:**
```json
{
  "run_id": "run_20240115_142345",
  "generation": 5,
  "timestamp": "2024-01-15 14:45:30.000",
  "num_individuals": 20,
  "best_score": 0.95,
  "avg_score": 0.82,
  "pareto_size": 3,
  "total_cost": 1.25,
  "metadata": "{\"median_score\":0.83,\"std_dev\":0.08,\"elite_count\":5}"
}
```

**Key Queries:**
```sql
-- Fitness trajectory
SELECT generation, best_score, avg_score, total_cost
FROM generations
WHERE run_id = 'run_20240115_142345'
ORDER BY generation;

-- Cost per generation
SELECT generation, total_cost, total_cost / num_individuals as cost_per_individual
FROM generations
WHERE run_id = 'run_20240115_142345';

-- Identify breakthrough generations (large improvement)
SELECT 
    generation,
    best_score,
    best_score - lag(best_score) OVER (ORDER BY generation) as improvement
FROM generations
WHERE run_id = 'run_20240115_142345'
ORDER BY improvement DESC;
```

---

#### `individuals`
**Purpose:** Store detailed information about every code variant evaluated during evolution. This is the most granular table.

**Use Cases:**
- Find the best individual ever created
- Track diversity in the population
- Analyze which mutation types produce the best offspring
- Debug why certain individuals scored poorly
- Deduplicate identical code variants

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `run_id` | String | Links to `evolution_runs.run_id` |
| `individual_id` | String | Unique identifier for this code variant (e.g., "ind_gen5_123") |
| `generation` | Int32 | Which generation this individual belongs to |
| `timestamp` | DateTime64(3) | When this individual was evaluated |
| `parent_id` | String | ID of the parent individual (empty string for initial population) |
| `mutation_type` | String | How this individual was created: "init" (initial), "mutate" (single parent), "crossover" (two parents) |
| `fitness_score` | Float64 | Primary objective score (e.g., accuracy, solution quality) |
| `combined_score` | Float64 | Multi-objective combined score (if using Pareto optimization) |
| `metrics` | String | JSON of all evaluation metrics: `{"accuracy": 0.95, "size": 1024, "speed": 2.5}` |
| `is_pareto` | Bool | Whether this individual is on the Pareto frontier for this generation |
| `api_cost` | Float64 | Cost to generate this individual (LLM mutation/crossover cost) |
| `embed_cost` | Float64 | Cost to compute embeddings for this individual |
| `novelty_cost` | Float64 | Cost to compute novelty score (if using novelty search) |
| `code_hash` | String | SHA-256 hash of the code (for detecting duplicates) |
| `code_size` | Int32 | Size of code in bytes |

**Example Row:**
```json
{
  "run_id": "run_20240115_142345",
  "individual_id": "ind_gen5_123",
  "generation": 5,
  "timestamp": "2024-01-15 14:45:30.123",
  "parent_id": "ind_gen4_087",
  "mutation_type": "mutate",
  "fitness_score": 0.95,
  "combined_score": 0.90,
  "metrics": "{\"accuracy\":0.95,\"size\":1024,\"speed\":2.5,\"memory\":512}",
  "is_pareto": true,
  "api_cost": 0.05,
  "embed_cost": 0.001,
  "novelty_cost": 0.002,
  "code_hash": "a3f5d8b9c1e2...",
  "code_size": 1024
}
```

**Key Queries:**
```sql
-- Top 10 individuals ever created
SELECT individual_id, generation, fitness_score, mutation_type, metrics
FROM individuals
WHERE run_id = 'run_20240115_142345'
ORDER BY fitness_score DESC
LIMIT 10;

-- Duplicates (same code hash)
SELECT code_hash, count(*) as count
FROM individuals
WHERE run_id = 'run_20240115_142345'
GROUP BY code_hash
HAVING count > 1;

-- Mutation type effectiveness
SELECT 
    mutation_type,
    count() as count,
    avg(fitness_score) as avg_fitness,
    max(fitness_score) as max_fitness
FROM individuals
WHERE run_id = 'run_20240115_142345' AND generation > 0
GROUP BY mutation_type
ORDER BY avg_fitness DESC;

-- Pareto frontier members across all generations
SELECT generation, individual_id, fitness_score, combined_score
FROM individuals
WHERE run_id = 'run_20240115_142345' AND is_pareto = true
ORDER BY generation, fitness_score DESC;
```

---

#### `pareto_fronts`
**Purpose:** Snapshot of the Pareto frontier at each generation. Stores which individuals were non-dominated for multi-objective optimization.

**Use Cases:**
- Track how the Pareto frontier evolves over time
- Visualize trade-offs between objectives
- Compare Pareto sets across different runs
- Identify when the frontier stops improving

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `run_id` | String | Links to `evolution_runs.run_id` |
| `generation` | Int32 | Which generation this Pareto snapshot is from |
| `timestamp` | DateTime64(3) | When this Pareto frontier was computed |
| `individual_id` | String | ID of an individual on the Pareto frontier (links to `individuals`) |
| `fitness_score` | Float64 | Primary objective score |
| `combined_score` | Float64 | Combined multi-objective score |
| `metrics` | String | JSON of all metrics (for plotting trade-offs) |

**Example Rows (Pareto frontier for generation 5):**
```json
[
  {
    "run_id": "run_20240115_142345",
    "generation": 5,
    "individual_id": "ind_gen5_001",
    "fitness_score": 0.95,
    "combined_score": 0.85,
    "metrics": "{\"accuracy\":0.95,\"size\":2048}"
  },
  {
    "generation": 5,
    "individual_id": "ind_gen5_042",
    "fitness_score": 0.90,
    "combined_score": 0.88,
    "metrics": "{\"accuracy\":0.90,\"size\":512}"
  }
]
```

**Key Queries:**
```sql
-- Pareto frontier size over time
SELECT generation, count(*) as pareto_size
FROM pareto_fronts
WHERE run_id = 'run_20240115_142345'
GROUP BY generation
ORDER BY generation;

-- Latest Pareto frontier
SELECT individual_id, fitness_score, combined_score, metrics
FROM pareto_fronts
WHERE run_id = 'run_20240115_142345'
  AND generation = (SELECT max(generation) FROM pareto_fronts WHERE run_id = 'run_20240115_142345')
ORDER BY fitness_score DESC;

-- Compare Pareto fronts across generations
SELECT generation, individual_id, 
       JSONExtractFloat(metrics, 'accuracy') as accuracy,
       JSONExtractFloat(metrics, 'size') as size
FROM pareto_fronts
WHERE run_id = 'run_20240115_142345'
ORDER BY generation, accuracy DESC;
```

---

#### `code_lineages`
**Purpose:** Track parent-child relationships between code variants. Essential for phylogenetic analysis and understanding evolutionary paths.

**Use Cases:**
- Build evolutionary tree visualizations
- Trace lineage of best individuals back to initial population
- Identify prolific parents (many successful offspring)
- Analyze which mutations led to breakthroughs
- Detect evolutionary dead ends

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `run_id` | String | Links to `evolution_runs.run_id` |
| `child_id` | String | ID of the child individual (links to `individuals.individual_id`) |
| `parent_id` | String | ID of the parent individual (empty for initial population) |
| `generation` | Int32 | Generation in which the child was created |
| `mutation_type` | String | How the child was created: "init", "mutate", "crossover" |
| `timestamp` | DateTime64(3) | When this lineage relationship was created |
| `fitness_delta` | Float64 | Change in fitness from parent to child (child_fitness - parent_fitness) |
| `edit_summary` | String | Human-readable description of what changed (from LLM summary) |

**Example Row:**
```json
{
  "run_id": "run_20240115_142345",
  "child_id": "ind_gen5_123",
  "parent_id": "ind_gen4_087",
  "generation": 5,
  "mutation_type": "mutate",
  "timestamp": "2024-01-15 14:45:30.456",
  "fitness_delta": 0.05,
  "edit_summary": "Optimized loop to use vectorized operations, reducing time complexity from O(n²) to O(n)"
}
```

**Key Queries:**
```sql
-- Most successful mutations (biggest improvements)
SELECT child_id, parent_id, generation, mutation_type, fitness_delta, edit_summary
FROM code_lineages
WHERE run_id = 'run_20240115_142345' AND fitness_delta > 0
ORDER BY fitness_delta DESC
LIMIT 10;

-- Mutation success rate
SELECT 
    mutation_type,
    count() as total,
    countIf(fitness_delta > 0) as improvements,
    countIf(fitness_delta > 0) / count() as success_rate,
    avg(fitness_delta) as avg_delta
FROM code_lineages
WHERE run_id = 'run_20240115_142345' AND generation > 0
GROUP BY mutation_type;

-- Trace lineage of best individual
WITH RECURSIVE lineage AS (
    SELECT child_id as id, parent_id, generation, mutation_type, edit_summary
    FROM code_lineages
    WHERE child_id = 'ind_gen10_best'  -- Start with best individual
    
    UNION ALL
    
    SELECT c.child_id, c.parent_id, c.generation, c.mutation_type, c.edit_summary
    FROM code_lineages c
    INNER JOIN lineage l ON c.child_id = l.parent_id
)
SELECT * FROM lineage ORDER BY generation;

-- Most prolific parents (many children)
SELECT 
    parent_id,
    count() as num_children,
    avg(fitness_delta) as avg_improvement,
    countIf(fitness_delta > 0) as successful_children
FROM code_lineages
WHERE run_id = 'run_20240115_142345'
GROUP BY parent_id
ORDER BY num_children DESC
LIMIT 20;
```

---

## Table Relationships

```
evolution_runs (1)
    ↓
    ├─→ generations (many)
    │       ↓
    │       └─→ individuals (many)
    │               ↓
    │               ├─→ pareto_fronts (subset)
    │               └─→ code_lineages (parent-child edges)
    │
    └─→ llm_logs (many, via metadata)
    └─→ agent_actions (many, via details)
```

**Data Flow:**
1. **Run starts** → Insert into `evolution_runs`
2. **Generation completes** → Insert into `generations`
3. **Individual evaluated** → Insert into `individuals`
4. **Pareto computed** → Insert into `pareto_fronts`
5. **Child created** → Insert into `code_lineages`
6. **LLM called** → Insert into `llm_logs`
7. **Action occurs** → Insert into `agent_actions`

## Usage in Code

### When to Log What

```
Evolution Run Lifecycle:
┌─────────────────────────────────────────────────────────────┐
│ 1. Run Starts                                               │
│    └─> log_evolution_run(run_id, task, config, ...)        │
├─────────────────────────────────────────────────────────────┤
│ 2. For Each Generation:                                     │
│    ├─> For Each Individual:                                 │
│    │   ├─> LLM Call (auto-logged via llm_logs)             │
│    │   ├─> Evaluation                                       │
│    │   ├─> log_individual(...)                              │
│    │   └─> log_lineage(child, parent, ...)                 │
│    ├─> Compute Pareto Frontier                              │
│    ├─> log_pareto_front(...)                                │
│    └─> log_generation(gen, best_score, avg_score, ...)     │
├─────────────────────────────────────────────────────────────┤
│ 3. Run Completes                                            │
│    └─> update_evolution_run(run_id, "completed", gens)     │
└─────────────────────────────────────────────────────────────┘

System Events (Logged Automatically):
  • job_submitted → agent_actions
  • job_completed → agent_actions
  • LLM calls → llm_logs
```

### Logging Evolution Data

```python
from genesis.utils.clickhouse_logger import ch_logger

# Start of evolution run
ch_logger.log_evolution_run(
    run_id="run_12345",
    task_name="circle_packing",
    config=cfg,  # Hydra config dict
    population_size=20,
    cluster_type="local",
    database_path="results/circle_packing.db",
)

# Each generation
ch_logger.log_generation(
    run_id="run_12345",
    generation=5,
    num_individuals=20,
    best_score=0.95,
    avg_score=0.82,
    pareto_size=3,
    total_cost=1.25,
)

# Each individual evaluation
ch_logger.log_individual(
    run_id="run_12345",
    individual_id="ind_001",
    generation=5,
    parent_id="ind_parent",
    mutation_type="mutate",
    fitness_score=0.95,
    combined_score=0.90,
    metrics={"accuracy": 0.95, "size": 1024},
    is_pareto=True,
    api_cost=0.05,
)

# Track lineage
ch_logger.log_lineage(
    run_id="run_12345",
    child_id="ind_001",
    parent_id="ind_parent",
    generation=5,
    mutation_type="mutate",
    fitness_delta=0.05,
    edit_summary="Optimized loop algorithm",
)
```

### Logging LLM Calls (already integrated)

LLM calls are automatically logged via `genesis.llm.query.py`:

```python
ch_logger.log_llm_interaction(
    model="claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "..."}],
    response="...",
    cost=0.01,
    execution_time=2.5,
)
```

## Useful Queries

### Track Evolution Progress

```sql
-- Best score per generation
SELECT 
    generation,
    best_score,
    avg_score,
    pareto_size,
    total_cost
FROM generations
WHERE run_id = 'your_run_id'
ORDER BY generation;

-- Top 10 individuals across all generations
SELECT 
    individual_id,
    generation,
    fitness_score,
    combined_score,
    mutation_type
FROM individuals
WHERE run_id = 'your_run_id'
ORDER BY fitness_score DESC
LIMIT 10;
```

### Cost Analysis

```sql
-- Total costs by run
SELECT 
    run_id,
    task_name,
    sum(total_cost) as total_evolution_cost,
    count(DISTINCT generation) as generations
FROM generations
GROUP BY run_id, task_name
ORDER BY total_evolution_cost DESC;

-- LLM costs by model
SELECT 
    model,
    count() as calls,
    sum(cost) as total_cost,
    avg(execution_time) as avg_time
FROM llm_logs
GROUP BY model
ORDER BY total_cost DESC;
```

### Lineage Analysis

```sql
-- Most successful mutations (positive fitness delta)
SELECT 
    mutation_type,
    count() as count,
    avg(fitness_delta) as avg_improvement,
    max(fitness_delta) as best_improvement
FROM code_lineages
WHERE fitness_delta > 0
GROUP BY mutation_type
ORDER BY avg_improvement DESC;

-- Build phylogenetic tree
SELECT 
    child_id,
    parent_id,
    generation,
    mutation_type,
    fitness_delta
FROM code_lineages
WHERE run_id = 'your_run_id'
ORDER BY generation, timestamp;
```

### Pareto Frontier Evolution

```sql
-- Track how Pareto frontier changes over time
SELECT 
    generation,
    count(DISTINCT individual_id) as pareto_size,
    max(fitness_score) as max_fitness,
    min(combined_score) as min_combined
FROM pareto_fronts
WHERE run_id = 'your_run_id'
GROUP BY generation
ORDER BY generation;
```

## Schema Design Decisions

### Why ClickHouse?

1. **High Write Throughput** - Handle 1000s of individual evaluations per minute
2. **Fast Analytics** - Aggregate across millions of rows in milliseconds
3. **Time-Series Optimized** - Sorted by timestamp for efficient range queries
4. **Columnar Storage** - Only read columns you need (efficient for wide tables)
5. **JSON Support** - Flexible `metrics` and `config` fields without schema migrations

### MergeTree Engine

All tables use `ENGINE = MergeTree()` which:
- Sorts data by `ORDER BY` key for fast queries
- Compresses data efficiently (10x+ compression typical)
- Supports fast upserts and deletes (via mutations)
- Handles high insert rates without blocking reads

### Data Volume Estimates

For a typical run with **20 individuals × 10 generations**:

| Table | Rows | Storage (uncompressed) | Storage (compressed) |
|-------|------|------------------------|----------------------|
| `evolution_runs` | 1 | ~2 KB | ~500 bytes |
| `generations` | 10 | ~2 KB | ~500 bytes |
| `individuals` | 200 | ~100 KB | ~10 KB |
| `pareto_fronts` | ~50 | ~10 KB | ~2 KB |
| `code_lineages` | 200 | ~50 KB | ~5 KB |
| `llm_logs` | ~400 | ~2 MB | ~200 KB |
| `agent_actions` | ~500 | ~200 KB | ~20 KB |
| **Total** | **~1361** | **~2.4 MB** | **~240 KB** |

**Scaling:**
- 1000 runs → ~240 MB (compressed)
- 10,000 runs → ~2.4 GB (compressed)

ClickHouse handles this easily. Even with millions of individuals, queries remain fast.

## Data Retention

ClickHouse is designed for high-volume data. Consider setting TTL policies for log tables:

```sql
-- Keep LLM logs for 30 days (if you want to save space)
ALTER TABLE llm_logs 
MODIFY TTL timestamp + INTERVAL 30 DAY;

-- Keep agent actions for 90 days
ALTER TABLE agent_actions
MODIFY TTL timestamp + INTERVAL 90 DAY;

-- Keep evolution data forever
-- No TTL on: evolution_runs, generations, individuals, pareto_fronts, code_lineages
```

**Recommended:** Keep evolution tables (`individuals`, `pareto_fronts`, `code_lineages`) forever for reproducibility. They compress well and are essential for analyzing evolutionary dynamics.

## Visualization

You can connect ClickHouse to visualization tools:
- **Grafana** - Real-time dashboards
- **Metabase** - SQL-based exploration
- **Jupyter** - Python analysis with `clickhouse-connect`

Example Jupyter notebook:

```python
from clickhouse_connect import get_client
import pandas as pd

client = get_client(
    host='your-host',
    port=8443,
    username='default',
    password='your-password',
    secure=True
)

# Query as DataFrame
df = client.query_df("""
    SELECT generation, best_score, avg_score
    FROM generations
    WHERE run_id = 'run_12345'
    ORDER BY generation
""")

df.plot(x='generation', y=['best_score', 'avg_score'])
```

## Common Queries Cheatsheet

```sql
-- Find best individual across all runs for a task
SELECT i.run_id, i.individual_id, i.generation, i.fitness_score, i.metrics
FROM individuals i
JOIN evolution_runs r ON i.run_id = r.run_id
WHERE r.task_name = 'circle_packing'
ORDER BY i.fitness_score DESC
LIMIT 1;

-- Evolution progress dashboard
SELECT 
    g.generation,
    g.best_score,
    g.avg_score,
    g.pareto_size,
    g.total_cost,
    countIf(i.is_pareto) as pareto_actual
FROM generations g
LEFT JOIN individuals i ON g.run_id = i.run_id AND g.generation = i.generation
WHERE g.run_id = 'YOUR_RUN_ID'
GROUP BY g.generation, g.best_score, g.avg_score, g.pareto_size, g.total_cost
ORDER BY g.generation;

-- Cost breakdown by component
SELECT 
    sum(api_cost) as total_mutation_cost,
    sum(embed_cost) as total_embedding_cost,
    sum(novelty_cost) as total_novelty_cost,
    sum(api_cost + embed_cost + novelty_cost) as total_cost
FROM individuals
WHERE run_id = 'YOUR_RUN_ID';

-- Mutation type effectiveness
SELECT 
    mutation_type,
    count() as count,
    avg(fitness_score) as avg_fitness,
    quantile(0.5)(fitness_score) as median_fitness,
    quantile(0.9)(fitness_score) as p90_fitness
FROM individuals
WHERE run_id = 'YOUR_RUN_ID' AND generation > 0
GROUP BY mutation_type;

-- Find generations with breakthroughs (>10% improvement)
SELECT 
    generation,
    best_score,
    best_score - lagInFrame(best_score) OVER (ORDER BY generation) as improvement,
    improvement / lagInFrame(best_score) OVER (ORDER BY generation) as improvement_pct
FROM generations
WHERE run_id = 'YOUR_RUN_ID'
HAVING improvement_pct > 0.1
ORDER BY improvement_pct DESC;

-- LLM cost by model
SELECT 
    model,
    count() as calls,
    sum(cost) as total_cost,
    avg(cost) as avg_cost_per_call,
    sum(execution_time) as total_time_seconds
FROM llm_logs
GROUP BY model
ORDER BY total_cost DESC;
```

## Troubleshooting

### Connection Issues

**"ClickHouse logging disabled"**
- Check `CLICKHOUSE_URL` is set: `echo $CLICKHOUSE_URL`
- Verify format: `https://user:password@host:port/database`
- Test connection: `python scripts/test_clickhouse.py`

**"clickhouse-connect not installed"**
```bash
uv pip install clickhouse-connect
```

**"Connection refused"**
- Check host/port are correct
- Verify firewall allows outbound connections to ClickHouse port
- For ClickHouse Cloud, ensure you're using HTTPS (port 8443) not HTTP (port 8123)

### Data Issues

**"No data in tables"**
- Tables are created automatically but only populated when you integrate logging calls
- Check `llm_logs` and `agent_actions` - these are auto-populated by existing code
- Evolution tables (`evolution_runs`, `individuals`, etc.) require integration in `runner.py`

**"Duplicate data"**
- ClickHouse MergeTree allows duplicates by default
- Use `code_hash` to deduplicate individuals
- Set up a `ReplacingMergeTree` if you need automatic deduplication

**"Queries are slow"**
- Always filter by `run_id` when possible (it's in the ORDER BY key)
- Use `timestamp` ranges for time-based queries
- Avoid `SELECT *` - specify only needed columns

## Next Steps

To integrate ClickHouse logging into your evolution runs:

1. **Update `runner.py`** - Add calls to `log_evolution_run`, `log_generation`, `log_individual`
2. **Update evaluation** - Log individual metrics after each evaluation
3. **Track Pareto** - Call `log_pareto_front` after each generation
4. **Set up dashboards** - Create Grafana dashboards for real-time monitoring

See `genesis/utils/clickhouse_logger.py` for the full API.

## References

- [ClickHouse Documentation](https://clickhouse.com/docs)
- [clickhouse-connect Python Client](https://clickhouse.com/docs/en/integrations/python)
- [ClickHouse SQL Reference](https://clickhouse.com/docs/en/sql-reference)
- [MergeTree Engine](https://clickhouse.com/docs/en/engines/table-engines/mergetree-family/mergetree)
