import json
import logging
import time
import os
import math
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import clickhouse_connect

from .complexity import analyze_code_metrics
from .parents import CombinedParentSelector
from .inspirations import CombinedContextSelector
from .islands import CombinedIslandManager
from .display import DatabaseDisplay
from genesis.llm.embedding import EmbeddingClient

logger = logging.getLogger(__name__)


def clean_nan_values(obj: Any) -> Any:
    """
    Recursively clean NaN values from a data structure, replacing them with
    None. This ensures JSON serialization works correctly.
    """
    if isinstance(obj, dict):
        return {key: clean_nan_values(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(clean_nan_values(item) for item in obj)
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, np.floating) and (np.isnan(obj) or np.isinf(obj)):
        return None
    elif hasattr(obj, "dtype") and np.issubdtype(obj.dtype, np.floating):
        if np.isscalar(obj):
            return None if (np.isnan(obj) or np.isinf(obj)) else float(obj)
        else:
            return clean_nan_values(obj.tolist())
    else:
        return obj


@dataclass
class DatabaseConfig:
    host: str = None
    port: int = None
    username: str = None
    password: str = None
    database: str = None
    secure: bool = False

    def __post_init__(self):
        """Parse ClickHouse URL if provided, otherwise use individual env vars."""
        import re

        clickhouse_url = os.getenv("CLICKHOUSE_URL")

        if clickhouse_url:
            # Parse URL format: https://user:password@host:port or http://host:port
            match = re.match(r"https?://([^:]+):([^@]+)@([^:]+):(\d+)", clickhouse_url)
            if match:
                self.username = match.group(1)
                self.password = match.group(2)
                self.host = match.group(3)
                self.port = int(match.group(4))
                self.secure = clickhouse_url.startswith("https")
                self.database = "default"
            else:
                raise ValueError(f"Invalid CLICKHOUSE_URL format: {clickhouse_url}")
        else:
            # Use individual env vars if URL not provided
            self.host = self.host or os.getenv("CLICKHOUSE_HOST", "localhost")
            self.port = self.port or int(os.getenv("CLICKHOUSE_PORT", 8123))
            self.username = self.username or os.getenv("CLICKHOUSE_USER", "default")
            self.password = self.password or os.getenv("CLICKHOUSE_PASSWORD", "")
            self.database = self.database or os.getenv("CLICKHOUSE_DB", "default")
            self.secure = False

    num_islands: int = 4
    archive_size: int = 100

    # Inspiration parameters
    elite_selection_ratio: float = 0.3
    num_archive_inspirations: int = 5
    num_top_k_inspirations: int = 2

    # Island model/migration parameters
    migration_interval: int = 10
    migration_rate: float = 0.1
    island_elitism: bool = True
    enforce_island_separation: bool = True

    # Parent selection parameters
    parent_selection_strategy: str = "power_law"

    # Power-law parent selection parameters
    exploitation_alpha: float = 1.0
    exploitation_ratio: float = 0.2

    # Weighted tree parent selection parameters
    parent_selection_lambda: float = 10.0

    # Beam search parent selection parameters
    num_beams: int = 5

    # Embedding model name
    embedding_model: str = "text-embedding-3-small"


@dataclass
class Program:
    """Represents a program in the database"""

    id: str
    code: str
    language: str = "python"
    parent_id: Optional[str] = None
    archive_inspiration_ids: List[str] = field(default_factory=list)
    top_k_inspiration_ids: List[str] = field(default_factory=list)
    island_idx: Optional[int] = None
    generation: int = 0
    timestamp: float = field(default_factory=time.time)
    code_diff: Optional[str] = None
    combined_score: float = 0.0
    public_metrics: Dict[str, Any] = field(default_factory=dict)
    private_metrics: Dict[str, Any] = field(default_factory=dict)
    text_feedback: Union[str, List[str]] = ""
    correct: bool = False
    children_count: int = 0
    complexity: float = 0.0
    embedding: List[float] = field(default_factory=list)
    embedding_pca_2d: List[float] = field(default_factory=list)
    embedding_pca_3d: List[float] = field(default_factory=list)
    embedding_cluster_id: Optional[int] = None
    migration_history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    in_archive: bool = False
    thought: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return clean_nan_values(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Program":
        # Ensure fields are correct types
        for field_name in ["public_metrics", "private_metrics", "metadata"]:
            if not isinstance(data.get(field_name), dict):
                data[field_name] = {}

        for field_name in [
            "archive_inspiration_ids",
            "top_k_inspiration_ids",
            "embedding",
            "embedding_pca_2d",
            "embedding_pca_3d",
            "migration_history",
        ]:
            if not isinstance(data.get(field_name), list):
                data[field_name] = []

        # Filter fields
        program_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in program_fields}
        return cls(**filtered_data)


class ProgramDatabase:
    """
    ClickHouse-backed database for storing and managing programs.
    """

    def __init__(
        self,
        config: DatabaseConfig,
        embedding_model: str = "text-embedding-3-small",
        read_only: bool = False,
    ):
        self.config = config
        self.read_only = read_only
        self.client = None

        # Connect to ClickHouse
        try:
            self.client = clickhouse_connect.get_client(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
                database=self.config.database,
                secure=self.config.secure,
                connect_timeout=30,
                send_receive_timeout=60,
            )
            logger.info(
                f"Connected to ClickHouse at {self.config.host}:{self.config.port} (secure={self.config.secure})"
            )
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            raise

        if not read_only:
            self.embedding_client = EmbeddingClient(model_name=embedding_model)
            self._create_tables()
        else:
            self.embedding_client = None

        self.last_iteration: int = 0
        self.best_program_id: Optional[str] = None
        self.beam_search_parent_id: Optional[str] = None
        self._schedule_migration: bool = False

        self._load_metadata()

        # Initialize managers with ClickHouse client
        self.island_manager = CombinedIslandManager(
            client=self.client,
            config=self.config,
        )

        count = self._count_programs()
        logger.debug(f"DB initialized with {count} programs.")

    def _create_tables(self):
        # Programs table
        self.client.command("""
            CREATE TABLE IF NOT EXISTS programs (
                id String,
                code String,
                language String,
                parent_id String,
                archive_inspiration_ids String, -- JSON
                top_k_inspiration_ids String, -- JSON
                generation Int32,
                timestamp Float64,
                code_diff String,
                combined_score Float64,
                public_metrics String, -- JSON
                private_metrics String, -- JSON
                text_feedback String,
                complexity Float64,
                embedding Array(Float32),
                embedding_pca_2d String, -- JSON
                embedding_pca_3d String, -- JSON
                embedding_cluster_id Int32,
                correct UInt8,
                children_count Int32,
                metadata String, -- JSON
                island_idx Int32,
                migration_history String, -- JSON
                in_archive UInt8 DEFAULT 0
            ) ENGINE = ReplacingMergeTree(timestamp)
            ORDER BY id
        """)

        # Ensure 'thought' column exists (migration)
        try:
            self.client.command(
                "ALTER TABLE programs ADD COLUMN IF NOT EXISTS thought String"
            )
        except Exception as e:
            logger.warning(f"Could not add 'thought' column: {e}")

        # Archive table (simplified, just tracks IDs in archive)
        self.client.command("""
            CREATE TABLE IF NOT EXISTS archive (
                program_id String,
                timestamp DateTime64(3) DEFAULT now()
            ) ENGINE = ReplacingMergeTree()
            ORDER BY program_id
        """)

        # Metadata store
        self.client.command("""
            CREATE TABLE IF NOT EXISTS metadata_store (
                key String,
                value String,
                timestamp DateTime64(3) DEFAULT now()
            ) ENGINE = ReplacingMergeTree(timestamp)
            ORDER BY key
        """)

        logger.debug("ClickHouse tables ensured to exist.")

    def _count_programs(self) -> int:
        return self.client.command("SELECT count() FROM programs")

    def _load_metadata(self):
        try:
            # Use query() with ORDER BY and LIMIT to get latest value from ReplacingMergeTree
            last_iter_result = self.client.query(
                "SELECT value FROM metadata_store WHERE key = 'last_iteration' ORDER BY timestamp DESC LIMIT 1"
            )
            if last_iter_result.result_rows:
                self.last_iteration = int(last_iter_result.result_rows[0][0])
            else:
                self.last_iteration = 0

            best_id_result = self.client.query(
                "SELECT value FROM metadata_store WHERE key = 'best_program_id' ORDER BY timestamp DESC LIMIT 1"
            )
            if best_id_result.result_rows:
                best_id = best_id_result.result_rows[0][0]
                self.best_program_id = (
                    best_id if best_id and best_id != "None" else None
                )
            else:
                self.best_program_id = None

            beam_id_result = self.client.query(
                "SELECT value FROM metadata_store WHERE key = 'beam_search_parent_id' ORDER BY timestamp DESC LIMIT 1"
            )
            if beam_id_result.result_rows:
                beam_id = beam_id_result.result_rows[0][0]
                self.beam_search_parent_id = (
                    beam_id if beam_id and beam_id != "None" else None
                )
            else:
                self.beam_search_parent_id = None
        except Exception as e:
            logger.warning(f"Failed to load metadata: {e}")

    def _update_metadata(self, key: str, value: Any):
        if self.read_only:
            return
        val_str = str(value)
        self.client.insert(
            "metadata_store", [[key, val_str]], column_names=["key", "value"]
        )

    def add(self, program: Program, verbose: bool = False) -> str:
        if self.read_only:
            raise PermissionError("Read-only mode")

        self.island_manager.assign_island(program)

        if program.complexity == 0.0:
            try:
                metrics = analyze_code_metrics(program.code, program.language)
                program.complexity = metrics.get(
                    "complexity_score", float(len(program.code))
                )
                if not program.metadata:
                    program.metadata = {}
                program.metadata["code_analysis_metrics"] = metrics
            except:
                program.complexity = float(len(program.code))

        # Serialize fields
        row = [
            program.id,
            program.code,
            program.language,
            program.parent_id or "",
            json.dumps(program.archive_inspiration_ids),
            json.dumps(program.top_k_inspiration_ids),
            program.generation,
            program.timestamp,
            program.code_diff or "",
            program.combined_score or 0.0,
            json.dumps(program.public_metrics),
            json.dumps(program.private_metrics),
            str(program.text_feedback) if program.text_feedback else "",
            program.complexity,
            program.embedding,
            json.dumps(program.embedding_pca_2d),
            json.dumps(program.embedding_pca_3d),
            program.embedding_cluster_id or -1,
            1 if program.correct else 0,
            program.children_count,
            json.dumps(program.metadata),
            program.island_idx if program.island_idx is not None else -1,
            json.dumps(program.migration_history),
            1 if program.in_archive else 0,
            program.thought,
        ]

        self.client.insert(
            "programs",
            [row],
            column_names=[
                "id",
                "code",
                "language",
                "parent_id",
                "archive_inspiration_ids",
                "top_k_inspiration_ids",
                "generation",
                "timestamp",
                "code_diff",
                "combined_score",
                "public_metrics",
                "private_metrics",
                "text_feedback",
                "complexity",
                "embedding",
                "embedding_pca_2d",
                "embedding_pca_3d",
                "embedding_cluster_id",
                "correct",
                "children_count",
                "metadata",
                "island_idx",
                "migration_history",
                "in_archive",
                "thought",
            ],
        )

        # Update parent children count (ClickHouse specific: we update by inserting new row with incremented count?
        # No, simpler to just rely on count queries or updates. ReplacingMergeTree handles updates by key.
        # But we need to read parent first. For now, let's skip incrementing parent count in DB
        # and rely on 'SELECT count() FROM programs WHERE parent_id=...' if needed)

        self._update_archive(program)
        self._update_best_program(program)
        self._recompute_embeddings_and_clusters()

        if program.generation > self.last_iteration:
            self.last_iteration = program.generation
            self._update_metadata("last_iteration", self.last_iteration)

        if verbose:
            self._print_program_summary(program)

        if self.island_manager.needs_island_copies(program):
            self.island_manager.copy_program_to_islands(program)
            # Remove flag in DB? We just inserted it. Maybe update it.
            # For ClickHouse, updating metadata means inserting a new row with same ID.
            if program.metadata:
                program.metadata.pop("_needs_island_copies", None)
                self._update_program_metadata(program.id, program.metadata)

        if self.island_manager.should_schedule_migration(program):
            self._schedule_migration = True

        self.check_scheduled_operations()
        return program.id

    def _update_program_metadata(self, pid: str, metadata: dict):
        meta_json = json.dumps(metadata)
        self.client.command(
            f"ALTER TABLE programs UPDATE metadata = '{meta_json}' WHERE id = '{pid}'"
        )

    def get(self, program_id: str) -> Optional[Program]:
        try:
            result = self.client.query(
                f"SELECT * FROM programs WHERE id = '{program_id}'"
            )
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            cols = result.column_names
            data = dict(zip(cols, row))
            return self._program_from_dict(data)
        except Exception as e:
            logger.error(f"Error getting program {program_id}: {e}")
            return None

    def _program_from_dict(self, data: Dict[str, Any]) -> Program:
        # Deserialize JSON fields
        for field in ["public_metrics", "private_metrics", "metadata"]:
            if isinstance(data.get(field), str):
                try:
                    data[field] = json.loads(data[field])
                except:
                    data[field] = {}

        for field in [
            "archive_inspiration_ids",
            "top_k_inspiration_ids",
            "embedding_pca_2d",
            "embedding_pca_3d",
            "migration_history",
        ]:
            if isinstance(data.get(field), str):
                try:
                    data[field] = json.loads(data[field])
                except:
                    data[field] = []

        data["correct"] = bool(data.get("correct", 0))
        data["in_archive"] = bool(data.get("in_archive", 0))
        if "thought" not in data:
            data["thought"] = ""

        # Handle -1 defaults
        if data.get("island_idx") == -1:
            data["island_idx"] = None
        if data.get("embedding_cluster_id") == -1:
            data["embedding_cluster_id"] = None
        if data.get("parent_id") == "":
            data["parent_id"] = None

        return Program.from_dict(data)

    def _update_archive(self, program: Program):
        if not self.config.archive_size or not program.correct:
            return

        count = self.client.command("SELECT count() FROM archive")
        if count < self.config.archive_size:
            self.client.command(
                f"INSERT INTO archive (program_id) VALUES ('{program.id}')"
            )
        else:
            # Find worst in archive
            # We need to join archive with programs to get scores
            worst_res = self.client.query("""
                SELECT a.program_id, p.combined_score 
                FROM archive a 
                LEFT JOIN programs p ON a.program_id = p.id
                ORDER BY p.combined_score ASC LIMIT 1
            """)
            if worst_res.result_rows:
                worst_id, worst_score = worst_res.result_rows[0]
                if program.combined_score > worst_score:
                    self.client.command(
                        f"ALTER TABLE archive DELETE WHERE program_id = '{worst_id}'"
                    )
                    self.client.command(
                        f"INSERT INTO archive (program_id) VALUES ('{program.id}')"
                    )

    def _update_best_program(self, program: Program):
        if not program.correct:
            return

        if not self.best_program_id:
            self.best_program_id = program.id
            self._update_metadata("best_program_id", program.id)
            return

        current_best = self.get(self.best_program_id)
        if not current_best or (program.combined_score > current_best.combined_score):
            self.best_program_id = program.id
            self._update_metadata("best_program_id", program.id)
            logger.info(
                f"New best program: {program.id} (Score: {program.combined_score})"
            )

    def get_best_program(self, metric: Optional[str] = None) -> Optional[Program]:
        query = "SELECT * FROM programs WHERE correct = 1"
        if metric:
            # This is tricky with JSON metrics in ClickHouse.
            # We'd need JSON extraction functions.
            # Assuming basic combined_score for now if metric is complex
            logger.warning(
                "Custom metric sorting in ClickHouse requires JSON extract logic. Using combined_score."
            )

        query += " ORDER BY combined_score DESC LIMIT 1"
        res = self.client.query(query)
        if res.result_rows:
            return self._program_from_dict(
                dict(zip(res.column_names, res.result_rows[0]))
            )
        return None

    def get_top_programs(
        self, n: int = 10, metric: str = "combined_score", correct_only: bool = False
    ) -> List[Program]:
        where = "WHERE correct = 1" if correct_only else "WHERE 1=1"
        query = f"SELECT * FROM programs {where} ORDER BY combined_score DESC LIMIT {n}"
        res = self.client.query(query)
        return [
            self._program_from_dict(dict(zip(res.column_names, row)))
            for row in res.result_rows
        ]

    def get_programs_by_generation(self, generation: int) -> List[Program]:
        """Get all programs from a specific generation."""
        query = f"SELECT * FROM programs WHERE generation = {generation} ORDER BY combined_score DESC"
        res = self.client.query(query)
        return [
            self._program_from_dict(dict(zip(res.column_names, row)))
            for row in res.result_rows
        ]

    def _recompute_embeddings_and_clusters(self, num_clusters: int = 4):
        try:
            from sklearn.decomposition import PCA
            from sklearn.cluster import KMeans
        except ImportError:
            logger.warning("scikit-learn not installed, skipping clustering")
            return

        # Fetch all programs with embeddings
        query = "SELECT * FROM programs WHERE length(embedding) > 0"
        res = self.client.query(query)
        if not res.result_rows:
            return

        programs = [
            self._program_from_dict(dict(zip(res.column_names, row)))
            for row in res.result_rows
        ]

        if len(programs) < 3:
            return

        embeddings = [p.embedding for p in programs]
        X = np.array(embeddings)

        # PCA 2D
        pca_2d = PCA(n_components=2)
        X_2d = pca_2d.fit_transform(X)

        # PCA 3D
        pca_3d = PCA(n_components=3)
        X_3d = pca_3d.fit_transform(X)

        # KMeans
        kmeans = KMeans(n_clusters=min(num_clusters, len(X)), n_init=10)
        labels = kmeans.fit_predict(X)

        # Update programs
        updated_rows = []
        for i, program in enumerate(programs):
            program.embedding_pca_2d = X_2d[i].tolist()
            program.embedding_pca_3d = X_3d[i].tolist()
            program.embedding_cluster_id = int(labels[i])
            # Update timestamp to ensure this version wins in ReplacingMergeTree
            program.timestamp = time.time()

            updated_rows.append(
                [
                    program.id,
                    program.code,
                    program.language,
                    program.parent_id or "",
                    json.dumps(program.archive_inspiration_ids),
                    json.dumps(program.top_k_inspiration_ids),
                    program.generation,
                    program.timestamp,
                    program.code_diff,
                    program.combined_score,
                    json.dumps(program.public_metrics),
                    json.dumps(program.private_metrics),
                    program.text_feedback,
                    program.complexity,
                    program.embedding,
                    json.dumps(program.embedding_pca_2d),
                    json.dumps(program.embedding_pca_3d),
                    program.embedding_cluster_id,
                    1 if program.correct else 0,
                    program.children_count,
                    json.dumps(program.metadata),
                    program.island_idx if program.island_idx is not None else -1,
                    json.dumps(program.migration_history),
                    1 if program.in_archive else 0,
                    program.thought,
                ]
            )

        # Bulk insert
        self.client.insert(
            "programs",
            updated_rows,
            column_names=[
                "id",
                "code",
                "language",
                "parent_id",
                "archive_inspiration_ids",
                "top_k_inspiration_ids",
                "generation",
                "timestamp",
                "code_diff",
                "combined_score",
                "public_metrics",
                "private_metrics",
                "text_feedback",
                "complexity",
                "embedding",
                "embedding_pca_2d",
                "embedding_pca_3d",
                "embedding_cluster_id",
                "correct",
                "children_count",
                "metadata",
                "island_idx",
                "migration_history",
                "in_archive",
                "thought",
            ],
        )
        logger.info(f"Recomputed embeddings and clusters for {len(programs)} programs")

    def check_scheduled_operations(self):
        if self._schedule_migration:
            self.island_manager.perform_migration(self.last_iteration)
            self._schedule_migration = False

    def close(self):
        if self.client:
            self.client.close()

    def print_summary(self, console=None):
        pass  # Todo: update display logic

    def _print_program_summary(self, program):
        pass

    def _program_exists(self) -> bool:
        try:
            return self._count_programs() > 0
        except Exception:
            return False

    def _get_island_idx_for_program_id(self, program_id: str) -> Optional[int]:
        program = self.get(program_id)
        return program.island_idx if program is not None else None

    def _fallback_parent(self) -> Optional[Program]:
        """
        Return a robust fallback parent if strategy-based selection fails.

        Preference order:
        1. Current best (correct program)
        2. Highest-scoring program overall
        3. Most recent program
        """
        parent = self.get_best_program()
        if parent is not None:
            return parent

        res = self.client.query(
            """
            SELECT * FROM programs
            ORDER BY combined_score DESC, timestamp DESC
            LIMIT 1
            """
        )
        if res.result_rows:
            return self._program_from_dict(dict(zip(res.column_names, res.result_rows[0])))
        return None

    def sample(
        self,
        target_generation: Optional[int] = None,
        novelty_attempt: int = 1,
        max_novelty_attempts: int = 1,
        resample_attempt: int = 1,
        max_resample_attempts: int = 1,
    ) -> Tuple[Program, List[Program], List[Program]]:
        """
        Sample a parent and inspiration context for the next generation.
        """
        if not self._program_exists():
            raise ValueError("Cannot sample parent/context: database has no programs.")

        island_idx = None
        if (
            getattr(self.config, "enforce_island_separation", False)
            and getattr(self.config, "num_islands", 0) > 1
            and self.island_manager is not None
            and hasattr(self.island_manager.assignment_strategy, "get_initialized_islands")
        ):
            try:
                initialized_islands = (
                    self.island_manager.assignment_strategy.get_initialized_islands()
                )
                if initialized_islands:
                    island_idx = random.choice(initialized_islands)
            except Exception:
                island_idx = None

        parent_selector = CombinedParentSelector(
            client=self.client,
            config=self.config,
            get_program_func=self.get,
            best_program_id=self.best_program_id,
            beam_search_parent_id=self.beam_search_parent_id,
            last_iteration=self.last_iteration,
            update_metadata_func=self._update_metadata,
            get_best_program_func=self.get_best_program,
        )
        try:
            parent = parent_selector.sample_parent(island_idx=island_idx)
        except Exception:
            parent = None

        if parent is None:
            parent = self._fallback_parent()
        if parent is None:
            raise ValueError("Unable to sample a parent program from database.")

        context_selector = CombinedContextSelector(
            client=self.client,
            config=self.config,
            get_program_func=self.get,
            best_program_id=self.best_program_id,
            get_island_idx_func=self._get_island_idx_for_program_id,
        )

        num_archive = max(0, int(getattr(self.config, "num_archive_inspirations", 0)))
        num_top_k = max(0, int(getattr(self.config, "num_top_k_inspirations", 0)))

        try:
            archive_inspirations, top_k_inspirations = context_selector.sample_context(
                parent=parent,
                num_archive=num_archive,
                num_topk=num_top_k,
            )
        except Exception as e:
            logger.warning(f"Context sampling failed; continuing without inspirations: {e}")
            archive_inspirations, top_k_inspirations = [], []

        archive_inspirations = [p for p in archive_inspirations if p and p.id != parent.id]
        top_k_inspirations = [
            p for p in top_k_inspirations if p and p.id != parent.id
        ]

        # Deduplicate while preserving order
        seen: set[str] = set()
        dedup_archive = []
        for p in archive_inspirations:
            if p.id not in seen:
                seen.add(p.id)
                dedup_archive.append(p)

        seen_topk: set[str] = set()
        dedup_topk = []
        for p in top_k_inspirations:
            if p.id not in seen_topk and p.id not in seen:
                seen_topk.add(p.id)
                dedup_topk.append(p)

        return parent, dedup_archive, dedup_topk

    def _fetch_embedding_rows(
        self, island_idx: Optional[int] = None
    ) -> List[Tuple[str, List[float]]]:
        where = "WHERE length(embedding) > 0 AND correct = 1"
        if island_idx is not None:
            where += f" AND island_idx = {int(island_idx)}"

        res = self.client.query(f"SELECT id, embedding FROM programs {where}")
        rows: List[Tuple[str, List[float]]] = []
        for program_id, embedding in res.result_rows:
            if not embedding:
                continue
            rows.append((program_id, list(embedding)))
        return rows

    def compute_similarity(
        self, code_embedding: List[float], island_idx: Optional[int] = None
    ) -> List[float]:
        """
        Compute cosine similarities between a candidate embedding and existing
        programs (optionally limited to an island).
        """
        if not code_embedding:
            return []

        rows = self._fetch_embedding_rows(island_idx=island_idx)
        if not rows:
            return []

        query_vec = np.asarray(code_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(query_vec)
        if q_norm == 0:
            return []

        similarities: List[float] = []
        for _, emb in rows:
            emb_vec = np.asarray(emb, dtype=np.float32)
            if emb_vec.size != query_vec.size:
                continue
            emb_norm = np.linalg.norm(emb_vec)
            if emb_norm == 0:
                continue
            sim = float(np.dot(query_vec, emb_vec) / (q_norm * emb_norm))
            if math.isfinite(sim):
                similarities.append(sim)
        return similarities

    def get_most_similar_program(
        self, code_embedding: List[float], island_idx: Optional[int] = None
    ) -> Optional[Program]:
        """
        Return the most similar existing program by cosine similarity.
        """
        if not code_embedding:
            return None

        rows = self._fetch_embedding_rows(island_idx=island_idx)
        if not rows:
            return None

        query_vec = np.asarray(code_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(query_vec)
        if q_norm == 0:
            return None

        best_program_id: Optional[str] = None
        best_score = -1.0

        for program_id, emb in rows:
            emb_vec = np.asarray(emb, dtype=np.float32)
            if emb_vec.size != query_vec.size:
                continue
            emb_norm = np.linalg.norm(emb_vec)
            if emb_norm == 0:
                continue
            sim = float(np.dot(query_vec, emb_vec) / (q_norm * emb_norm))
            if math.isfinite(sim) and sim > best_score:
                best_score = sim
                best_program_id = program_id

        return self.get(best_program_id) if best_program_id else None
