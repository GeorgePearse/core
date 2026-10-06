import os
import logging
import json
import uuid
from datetime import datetime
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List

try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None

logger = logging.getLogger(__name__)


class ClickHouseLogger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ClickHouseLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.client = None
        self.enabled = False
        self._setup_client()
        self._initialized = True

    def _setup_client(self):
        url = os.getenv("CLICKHOUSE_URL")
        if not url:
            logger.warning(
                "CLICKHOUSE_URL not found in environment variables. ClickHouse logging disabled."
            )
            return

        if clickhouse_connect is None:
            logger.warning(
                "clickhouse-connect not installed. ClickHouse logging disabled."
            )
            return

        try:
            # Parse URL: https://user:password@host:port/database
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 8123)
            username = parsed.username or "default"
            password = parsed.password or ""
            database = parsed.path.lstrip("/") or "default"
            secure = parsed.scheme == "https"

            self.client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                secure=secure,
            )

            self._init_tables()
            self.enabled = True
            logger.info(f"Connected to ClickHouse at {host}:{port}/{database}")

        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            self.enabled = False

    def _init_tables(self):
        if not self.client:
            return

        try:
            # Table for LLM interactions (what agents say/hear)
            self.client.command("""
                CREATE TABLE IF NOT EXISTS llm_logs (
                    id UUID,
                    timestamp DateTime64(3),
                    model String,
                    messages String, -- JSON string of messages
                    response String,
                    thought String, -- Thinking process content
                    cost Float64,
                    execution_time Float64,
                    metadata String -- JSON string for extra info
                ) ENGINE = MergeTree()
                ORDER BY timestamp
            """)

            # Table for Agent Actions (what agents do)
            self.client.command("""
                CREATE TABLE IF NOT EXISTS agent_actions (
                    id UUID,
                    timestamp DateTime64(3),
                    action_type String,
                    details String, -- JSON string
                    metadata String -- JSON string
                ) ENGINE = MergeTree()
                ORDER BY timestamp
            """)

            # Table for Evolution Runs
            self.client.command("""
                CREATE TABLE IF NOT EXISTS evolution_runs (
                    run_id String,
                    start_time DateTime64(3),
                    end_time DateTime64(3) DEFAULT toDateTime64('1970-01-01 00:00:00', 3),
                    task_name String,
                    config String, -- JSON string of full config
                    status String, -- running, completed, failed
                    total_generations Int32,
                    population_size Int32,
                    cluster_type String,
                    database_path String
                ) ENGINE = MergeTree()
                ORDER BY start_time
            """)

            # Table for Generations
            self.client.command("""
                CREATE TABLE IF NOT EXISTS generations (
                    run_id String,
                    generation Int32,
                    timestamp DateTime64(3),
                    num_individuals Int32,
                    best_score Float64,
                    avg_score Float64,
                    pareto_size Int32,
                    total_cost Float64,
                    metadata String -- JSON string
                ) ENGINE = MergeTree()
                ORDER BY (run_id, generation)
            """)

            # Table for Individuals (code variants)
            self.client.command("""
                CREATE TABLE IF NOT EXISTS individuals (
                    run_id String,
                    individual_id String,
                    generation Int32,
                    timestamp DateTime64(3),
                    parent_id String,
                    mutation_type String, -- init, mutate, crossover
                    fitness_score Float64,
                    combined_score Float64,
                    metrics String, -- JSON string of all metrics
                    is_pareto Boolean,
                    api_cost Float64,
                    embed_cost Float64,
                    novelty_cost Float64,
                    code_hash String,
                    code_size Int32
                ) ENGINE = MergeTree()
                ORDER BY (run_id, generation, timestamp)
            """)

            # Table for Pareto Fronts (snapshot of pareto frontier per generation)
            self.client.command("""
                CREATE TABLE IF NOT EXISTS pareto_fronts (
                    run_id String,
                    generation Int32,
                    timestamp DateTime64(3),
                    individual_id String,
                    fitness_score Float64,
                    combined_score Float64,
                    metrics String -- JSON string
                ) ENGINE = MergeTree()
                ORDER BY (run_id, generation, fitness_score)
            """)

            # Table for Code Lineages (parent-child relationships)
            self.client.command("""
                CREATE TABLE IF NOT EXISTS code_lineages (
                    run_id String,
                    child_id String,
                    parent_id String,
                    generation Int32,
                    mutation_type String,
                    timestamp DateTime64(3),
                    fitness_delta Float64,
                    edit_summary String
                ) ENGINE = MergeTree()
                ORDER BY (run_id, generation, timestamp)
            """)

            logger.info("ClickHouse tables initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ClickHouse tables: {e}")
            self.enabled = False

    def log_llm_interaction(
        self,
        model: str,
        messages: List[Dict[str, Any]] | str,
        response: str,
        cost: float = 0.0,
        execution_time: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
        thought: str = "",
    ):
        if not self.enabled:
            return

        try:
            if not isinstance(messages, str):
                messages_str = json.dumps(messages)
            else:
                messages_str = messages

            metadata_str = json.dumps(metadata) if metadata else "{}"

            self.client.insert(
                "llm_logs",
                [
                    [
                        uuid.uuid4(),
                        datetime.now(),
                        model,
                        messages_str,
                        response,
                        thought,
                        cost,
                        execution_time,
                        metadata_str,
                    ]
                ],
                column_names=[
                    "id",
                    "timestamp",
                    "model",
                    "messages",
                    "response",
                    "thought",
                    "cost",
                    "execution_time",
                    "metadata",
                ],
            )
        except Exception as e:
            logger.error(f"Failed to log LLM interaction to ClickHouse: {e}")

    def log_action(
        self,
        action_type: str,
        details: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not self.enabled:
            return

        try:
            details_str = json.dumps(details) if details else "{}"
            metadata_str = json.dumps(metadata) if metadata else "{}"

            self.client.insert(
                "agent_actions",
                [
                    [
                        uuid.uuid4(),
                        datetime.now(),
                        action_type,
                        details_str,
                        metadata_str,
                    ]
                ],
                column_names=["id", "timestamp", "action_type", "details", "metadata"],
            )
        except Exception as e:
            logger.error(f"Failed to log action to ClickHouse: {e}")

    def log_evolution_run(
        self,
        run_id: str,
        task_name: str,
        config: Dict[str, Any],
        population_size: int,
        cluster_type: str,
        database_path: str,
        status: str = "running",
    ):
        """Log the start of an evolution run."""
        if not self.enabled:
            return

        try:
            config_str = json.dumps(config)
            self.client.insert(
                "evolution_runs",
                [
                    [
                        run_id,
                        datetime.now(),
                        datetime.fromtimestamp(0),  # end_time placeholder
                        task_name,
                        config_str,
                        status,
                        0,  # total_generations
                        population_size,
                        cluster_type,
                        database_path,
                    ]
                ],
                column_names=[
                    "run_id",
                    "start_time",
                    "end_time",
                    "task_name",
                    "config",
                    "status",
                    "total_generations",
                    "population_size",
                    "cluster_type",
                    "database_path",
                ],
            )
        except Exception as e:
            logger.error(f"Failed to log evolution run to ClickHouse: {e}")

    def update_evolution_run(self, run_id: str, status: str, total_generations: int):
        """Update an evolution run with completion info."""
        if not self.enabled:
            return

        try:
            self.client.command(
                f"""
                ALTER TABLE evolution_runs
                UPDATE 
                    end_time = now64(3),
                    status = '{status}',
                    total_generations = {total_generations}
                WHERE run_id = '{run_id}'
            """
            )
        except Exception as e:
            logger.error(f"Failed to update evolution run in ClickHouse: {e}")

    def log_generation(
        self,
        run_id: str,
        generation: int,
        num_individuals: int,
        best_score: float,
        avg_score: float,
        pareto_size: int,
        total_cost: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log generation-level statistics."""
        if not self.enabled:
            return

        try:
            metadata_str = json.dumps(metadata) if metadata else "{}"
            self.client.insert(
                "generations",
                [
                    [
                        run_id,
                        generation,
                        datetime.now(),
                        num_individuals,
                        best_score,
                        avg_score,
                        pareto_size,
                        total_cost,
                        metadata_str,
                    ]
                ],
                column_names=[
                    "run_id",
                    "generation",
                    "timestamp",
                    "num_individuals",
                    "best_score",
                    "avg_score",
                    "pareto_size",
                    "total_cost",
                    "metadata",
                ],
            )
        except Exception as e:
            logger.error(f"Failed to log generation to ClickHouse: {e}")

    def log_individual(
        self,
        run_id: str,
        individual_id: str,
        generation: int,
        parent_id: str,
        mutation_type: str,
        fitness_score: float,
        combined_score: float,
        metrics: Dict[str, Any],
        is_pareto: bool,
        api_cost: float = 0.0,
        embed_cost: float = 0.0,
        novelty_cost: float = 0.0,
        code_hash: str = "",
        code_size: int = 0,
    ):
        """Log an individual code variant evaluation."""
        if not self.enabled:
            return

        try:
            metrics_str = json.dumps(metrics)
            self.client.insert(
                "individuals",
                [
                    [
                        run_id,
                        individual_id,
                        generation,
                        datetime.now(),
                        parent_id,
                        mutation_type,
                        fitness_score,
                        combined_score,
                        metrics_str,
                        is_pareto,
                        api_cost,
                        embed_cost,
                        novelty_cost,
                        code_hash,
                        code_size,
                    ]
                ],
                column_names=[
                    "run_id",
                    "individual_id",
                    "generation",
                    "timestamp",
                    "parent_id",
                    "mutation_type",
                    "fitness_score",
                    "combined_score",
                    "metrics",
                    "is_pareto",
                    "api_cost",
                    "embed_cost",
                    "novelty_cost",
                    "code_hash",
                    "code_size",
                ],
            )
        except Exception as e:
            logger.error(f"Failed to log individual to ClickHouse: {e}")

    def log_pareto_front(
        self,
        run_id: str,
        generation: int,
        pareto_individuals: List[Dict[str, Any]],
    ):
        """Log the entire Pareto frontier for a generation."""
        if not self.enabled:
            return

        try:
            rows = []
            for ind in pareto_individuals:
                rows.append(
                    [
                        run_id,
                        generation,
                        datetime.now(),
                        ind["individual_id"],
                        ind["fitness_score"],
                        ind["combined_score"],
                        json.dumps(ind.get("metrics", {})),
                    ]
                )

            if rows:
                self.client.insert(
                    "pareto_fronts",
                    rows,
                    column_names=[
                        "run_id",
                        "generation",
                        "timestamp",
                        "individual_id",
                        "fitness_score",
                        "combined_score",
                        "metrics",
                    ],
                )
        except Exception as e:
            logger.error(f"Failed to log pareto front to ClickHouse: {e}")

    def log_lineage(
        self,
        run_id: str,
        child_id: str,
        parent_id: str,
        generation: int,
        mutation_type: str,
        fitness_delta: float = 0.0,
        edit_summary: str = "",
    ):
        """Log parent-child relationship in code evolution."""
        if not self.enabled:
            return

        try:
            self.client.insert(
                "code_lineages",
                [
                    [
                        run_id,
                        child_id,
                        parent_id,
                        generation,
                        mutation_type,
                        datetime.now(),
                        fitness_delta,
                        edit_summary,
                    ]
                ],
                column_names=[
                    "run_id",
                    "child_id",
                    "parent_id",
                    "generation",
                    "mutation_type",
                    "timestamp",
                    "fitness_delta",
                    "edit_summary",
                ],
            )
        except Exception as e:
            logger.error(f"Failed to log lineage to ClickHouse: {e}")


# Global instance
ch_logger = ClickHouseLogger()
