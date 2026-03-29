# Logging and Analytics 📊

Genesis provides robust logging capabilities to track evolutionary experiments, monitor LLM interactions, and analyze agent behavior. Beyond standard file-based logging, Genesis supports structured logging to ClickHouse for high-performance analytics.

## Standard Logging

By default, Genesis writes logs to the results directory of each experiment:

- **`evolution_run.log`**: Detailed logs of the evolutionary process, including job submissions, completions, and errors.
- **Console Output**: A cleaner, summarized view using `rich` for better readability.

## ClickHouse Logging 🚀

For production-grade experiments and deep analysis, Genesis integrates with [ClickHouse](https://clickhouse.com/), a high-performance open-source OLAP database. This allows you to store and query millions of evolutionary events, LLM thoughts, and code metrics in real-time.

### Why use ClickHouse?

- **Structured Data**: Query logs using SQL (e.g., "Show me all LLM responses that mentioned 'segmentation fault'").
- **Performance**: efficient compression and millisecond-latency queries on massive datasets.
- **Persistence**: Keep a permanent record of all experiments across different runs and machines.
- **Analytics**: Build dashboards (e.g., using Grafana or Metabase) on top of your experimental data.

### Prerequisites

1. **ClickHouse Server**: You need access to a ClickHouse server. You can:
   - Run one locally using Docker: `docker run -d -p 8123:8123 -p 9000:9000 --name clickhouse-server clickhouse/clickhouse-server`
   - Use a managed service like [ClickHouse Cloud](https://clickhouse.com/cloud).

2. **Python Dependency**: Install the `clickhouse-connect` driver:
   ```bash
   uv pip install clickhouse-connect
   # or
   pip install clickhouse-connect
   ```

### Configuration

To enable ClickHouse logging, simply set the `CLICKHOUSE_URL` environment variable. Genesis will automatically detect it and initialize the necessary tables.

```bash
# .env file or shell export
CLICKHOUSE_URL=http://default:@localhost:8123/default
```

**URL Format:**
`protocol://username:password@hostname:port/database`

Examples:
- Local (no auth): `http://default:@localhost:8123/default`
- Remote (secure): `https://admin:password@my-clickhouse-host.com:8443/genesis_db`

### Data Schema

Genesis automatically creates and manages the following tables:

| Table | Description | Key Columns |
|-------|-------------|-------------|
| **`llm_logs`** | All LLM inputs and outputs | `timestamp`, `model`, `messages`, `response`, `cost` |
| **`agent_actions`** | High-level agent decisions | `timestamp`, `action_type`, `details` |
| **`evolution_runs`** | Metadata about experiments | `run_id`, `task_name`, `config`, `status` |
| **`generations`** | Per-generation statistics | `run_id`, `generation`, `best_score`, `avg_score` |
| **`individuals`** | Details on every evolved program | `individual_id`, `fitness_score`, `code_hash`, `metrics` |
| **`code_lineages`** | Genealogy tracking | `parent_id`, `child_id`, `mutation_type`, `fitness_delta` |

### Example Queries

Here are some SQL queries you can run against your logs:

**1. Find the most expensive LLM calls:**
```sql
SELECT 
    model, 
    cost, 
    substring(response, 1, 100) as snippet 
FROM llm_logs 
ORDER BY cost DESC 
LIMIT 10
```

**2. Analyze improvement over generations:**
```sql
SELECT 
    generation, 
    max(best_score) as best, 
    avg(avg_score) as average 
FROM generations 
WHERE run_id = 'your-run-id' 
GROUP BY generation 
ORDER BY generation ASC
```

**3. Search for specific errors in LLM reasoning:**
```sql
SELECT 
    timestamp, 
    response 
FROM llm_logs 
WHERE response ILIKE '%error%' OR response ILIKE '%traceback%'
LIMIT 5
```

**4. Track lineage of a successful program:**
```sql
SELECT 
    generation, 
    mutation_type, 
    fitness_delta 
FROM code_lineages 
WHERE run_id = 'your-run-id' 
ORDER BY generation ASC
```
