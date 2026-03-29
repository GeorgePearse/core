import shutil
import uuid
import time
import logging
import yaml
from rich.logging import RichHandler
from rich.table import Table
from rich.console import Console
import rich.box
from typing import List, Optional, Union, cast
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from subprocess import Popen
from genesis.launch import JobScheduler, JobConfig, ProcessWithLogging
from genesis.database import ProgramDatabase, DatabaseConfig, Program
from genesis.llm import (
    LLMClient,
    extract_between,
    EmbeddingClient,
    BanditBase,
    AsymmetricUCB,
)
from genesis.edit import (
    apply_diff_patch,
    apply_full_patch,
    summarize_diff,
    redact_immutable,
)
from genesis.core.sampler import PromptSampler
from genesis.core.summarizer import MetaSummarizer
from genesis.core.novelty_judge import NoveltyJudge
from genesis.core.alma_memory import ALMAMemorySystem
from genesis.core.gepa_optimizer import GEPAStyleOptimizer
from genesis.logo import print_gradient_logo
from genesis.tools.web_search import search_web

FOLDER_PREFIX = "gen"


@dataclass
class EvolutionConfig:
    """Configuration for evolution loop.

    ARCHITECTURAL NOTE (SAGA Paper):
    Genesis currently implements SAGA's "inner loop" (solution optimization).
    Future extensions could add SAGA's "outer loop" (objective evolution):

    - Objective evolution: LLM modifies evaluate.py based on reward hacking
    - Bi-level optimization: Separate solution-level and objective-level
    - Multi-objective: Pareto frontier instead of single combined_score

    See docs/saga_integration.md for design details.
    """
    task_sys_msg: Optional[str] = None
    patch_types: List[str] = field(default_factory=lambda: ["diff"])
    patch_type_probs: List[float] = field(default_factory=lambda: [1.0])
    num_generations: int = 10
    max_parallel_jobs: int = 2
    max_patch_resamples: int = 3
    max_patch_attempts: int = 5
    job_type: str = "local"
    language: str = "python"
    llm_models: List[str] = field(default_factory=lambda: ["azure-gpt-4.1-mini"])
    llm_dynamic_selection: Optional[Union[str, BanditBase]] = None
    llm_dynamic_selection_kwargs: dict = field(default_factory=lambda: {})
    llm_kwargs: dict = field(default_factory=lambda: {})
    meta_rec_interval: Optional[int] = None
    meta_llm_models: Optional[List[str]] = None
    meta_llm_kwargs: dict = field(default_factory=lambda: {})
    meta_max_recommendations: int = 5
    embedding_model: Optional[str] = None
    init_program_path: Optional[str] = "initial.py"
    results_dir: Optional[str] = None
    max_novelty_attempts: int = 3
    code_embed_sim_threshold: float = 1.0
    novelty_llm_models: Optional[List[str]] = None
    novelty_llm_kwargs: dict = field(default_factory=lambda: {})
    use_text_feedback: bool = False
    # ALMA-style long-term memory
    alma_enabled: bool = False
    alma_max_entries: int = 256
    alma_max_retrievals: int = 4
    alma_min_success_delta: float = 0.0
    # GEPA-style prompt optimization (DSPy-inspired)
    gepa_enabled: bool = False
    gepa_num_fewshot_traces: int = 3
    gepa_max_traces: int = 64
    gepa_min_improvement: float = 0.0
    gepa_exploration_weight: float = 1.1
    gepa_candidate_instructions: Optional[List[str]] = None

    # Web search
    web_search_enabled: bool = False
    web_search_prob: float = 0.1

    # Git tracking and strategy metadata
    git_commit_sha: Optional[str] = None
    git_dirty: bool = False
    git_branch: Optional[str] = None
    strategy_name: str = "default"


@dataclass
class RunningJob:
    """Represents a running job in the queue."""

    job_id: Union[str, Popen, ProcessWithLogging]
    exec_fname: str
    results_dir: str
    start_time: float
    generation: int
    parent_id: Optional[str]
    archive_insp_ids: List[str]
    top_k_insp_ids: List[str]
    code_diff: Optional[str]
    meta_patch_data: Optional[dict]
    code_embedding: List[float] = field(default_factory=list)
    embed_cost: float = 0.0
    novelty_cost: float = 0.0


# Set up logging
logger = logging.getLogger(__name__)


class EvolutionRunner:
    """Main evolution loop - maps to SAGA Optimizer module.

    MODULAR ARCHITECTURE NOTE (SAGA Paper Comparison):
    This class implicitly combines all four SAGA modules:
    - Planner: meta_recommendations (strategic guidance)
    - Implementer: patch sampling and application
    - Optimizer: parent selection, islands, evolution loop
    - Analyzer: evaluation result processing

    Future refactoring could extract these into separate modules with
    clean interfaces for better extensibility and testability.

    See docs/modular_architecture.md for refactoring plan.
    """

    def __init__(
        self,
        evo_config: EvolutionConfig,
        job_config: JobConfig,
        db_config: DatabaseConfig,
        verbose: bool = True,
    ):
        self.evo_config = evo_config
        self.job_config = job_config
        self.db_config = db_config
        self.verbose = verbose

        print_gradient_logo((255, 0, 0), (255, 255, 255))
        if evo_config.results_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.results_dir = f"results_{timestamp}"
        else:
            self.results_dir = Path(evo_config.results_dir)

        if self.verbose:
            # Create log file path in results directory
            log_filename = f"{self.results_dir}/evolution_run.log"
            Path(self.results_dir).mkdir(parents=True, exist_ok=True)

            # Set up logging with both console and file handlers
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
                handlers=[
                    RichHandler(
                        show_time=False, show_level=False, show_path=False
                    ),  # Console output (clean)
                    logging.FileHandler(
                        log_filename, mode="a", encoding="utf-8"
                    ),  # File output (detailed)
                ],
            )

            # Also log the initial setup information
            logger.info("=" * 80)
            start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Evolution run started at {start_time}")
            logger.info(f"Results directory: {self.results_dir}")
            logger.info(f"Log file: {log_filename}")
            logger.info("=" * 80)

        # Initialize LLM selection strategy
        if evo_config.llm_dynamic_selection is None:
            self.llm_selection = None
        elif isinstance(evo_config.llm_dynamic_selection, BanditBase):
            self.llm_selection = evo_config.llm_dynamic_selection
        elif (evo_config.llm_dynamic_selection.lower() == "ucb") or (
            evo_config.llm_dynamic_selection.lower() == "ucb1"
        ):
            self.llm_selection = AsymmetricUCB(
                arm_names=evo_config.llm_models,
                **evo_config.llm_dynamic_selection_kwargs,
            )
        else:
            raise ValueError("Invalid llm_dynamic_selection")

        # Initialize database (using ClickHouse, not SQLite)
        embedding_model_to_use = evo_config.embedding_model or "text-embedding-3-small"
        self.db = ProgramDatabase(
            config=db_config, embedding_model=embedding_model_to_use
        )
        self.scheduler = JobScheduler(
            job_type=evo_config.job_type,
            config=job_config,  # type: ignore
            verbose=verbose,
        )

        self.llm = LLMClient(
            model_names=evo_config.llm_models,
            model_selection=self.llm_selection,
            **evo_config.llm_kwargs,
            verbose=verbose,
        )
        if evo_config.embedding_model is not None:
            self.embedding = EmbeddingClient(
                model_name=evo_config.embedding_model,
                verbose=verbose,
            )
        else:
            self.embedding = None

        if evo_config.meta_llm_models is not None:
            self.meta_llm = LLMClient(
                model_names=evo_config.meta_llm_models,
                **evo_config.meta_llm_kwargs,
                verbose=verbose,
            )
        else:
            self.meta_llm = None

        if evo_config.novelty_llm_models is not None:
            self.novelty_llm = LLMClient(
                model_names=evo_config.novelty_llm_models,
                **evo_config.novelty_llm_kwargs,
                verbose=verbose,
            )
        else:
            self.novelty_llm = None

        # Initialize PromptSampler for handling LLM code prompts
        self.prompt_sampler = PromptSampler(
            task_sys_msg=evo_config.task_sys_msg,
            language=evo_config.language,
            patch_types=evo_config.patch_types,
            patch_type_probs=evo_config.patch_type_probs,
            use_text_feedback=evo_config.use_text_feedback,
        )

        # Initialize MetaSummarizer for meta-recommendations
        self.meta_summarizer = MetaSummarizer(
            meta_llm_client=self.meta_llm,
            language=evo_config.language,
            use_text_feedback=evo_config.use_text_feedback,
            max_recommendations=evo_config.meta_max_recommendations,
        )

        # Initialize NoveltyJudge for novelty assessment
        self.novelty_judge = NoveltyJudge(
            novelty_llm_client=self.novelty_llm,
            language=evo_config.language,
            similarity_threshold=evo_config.code_embed_sim_threshold,
            max_novelty_attempts=evo_config.max_novelty_attempts,
        )

        self.alma_memory = ALMAMemorySystem(
            enabled=evo_config.alma_enabled,
            max_entries=evo_config.alma_max_entries,
            max_retrievals=evo_config.alma_max_retrievals,
            min_success_delta=evo_config.alma_min_success_delta,
        )

        # Initialize rich console for formatted output
        self.console = Console()

        self.gepa_optimizer = GEPAStyleOptimizer(
            enabled=evo_config.gepa_enabled,
            num_fewshot_traces=evo_config.gepa_num_fewshot_traces,
            max_traces=evo_config.gepa_max_traces,
            min_improvement=evo_config.gepa_min_improvement,
            exploration_weight=evo_config.gepa_exploration_weight,
            candidate_instructions=evo_config.gepa_candidate_instructions,
        )

        if self.evo_config.language == "cuda":
            self.lang_ext = "cu"
        elif self.evo_config.language == "cpp":
            self.lang_ext = "cpp"
        elif self.evo_config.language == "python":
            self.lang_ext = "py"
        elif self.evo_config.language == "rust":
            self.lang_ext = "rs"
        elif self.evo_config.language == "swift":
            self.lang_ext = "swift"
        elif self.evo_config.language in ["json", "json5"]:
            self.lang_ext = "json"
        else:
            msg = f"Language {self.evo_config.language} not supported"
            raise ValueError(msg)

        # Queue for managing parallel jobs
        self.running_jobs: List[RunningJob] = []
        self.best_program_id: Optional[str] = None
        self.next_generation_to_submit = 0

        # Generate unique run ID for ClickHouse tracking or resume existing
        self.run_id = None
        if Path(self.results_dir).exists():
            try:
                from genesis.utils.clickhouse_logger import ch_logger

                existing_run_id = ch_logger.get_run_id_by_path(str(self.results_dir))
                if existing_run_id:
                    self.run_id = existing_run_id
                    logger.info(f"Resuming existing run: {self.run_id}")
            except Exception as e:
                logger.warning(f"Failed to check for existing run_id: {e}")

        if not self.run_id:
            self.run_id = (
                f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            )

        # Track which generations have been logged to ClickHouse
        self.logged_generations = set()

        # If resuming, populate logged_generations from DB
        if self.run_id:
            try:
                # We need to access the raw client for this check
                # Note: db.client is exposed in ProgramDatabase
                query = f"SELECT distinct generation FROM generations WHERE run_id = '{self.run_id}'"
                # Check if table exists first? Or rely on try/except
                # The tables are created by ch_logger on init, but db.client might be different instance?
                # Actually ProgramDatabase creates its own client, but ch_logger has one too.
                # Use db.client since we know it's connected.
                res = self.db.client.query(query)
                if res.result_rows:
                    self.logged_generations = {row[0] for row in res.result_rows}
            except Exception as e:
                # Table might not exist yet if this is a fresh run and logger hasn't created it
                # or if connection failed.
                pass

        # Initialize generation counters based on DB state
        self.completed_generations = 0
        self.next_generation_to_submit = 0

        # Update counters to reflect existing progress (if any)
        self._update_completed_generations()

        # Save experiment configuration to a YAML file
        self._save_experiment_config(evo_config, job_config, db_config)
        self._restore_alma_memory()

        # Try restoring GEPA state if this is a resumed run
        self._restore_gepa_state()

    def _save_experiment_config(
        self,
        evo_config: EvolutionConfig,
        job_config: JobConfig,
        db_config: DatabaseConfig,
    ) -> None:
        """Save experiment configuration to a YAML file."""
        config_data = {
            "evolution_config": asdict(evo_config),
            "job_config": asdict(job_config),
            "database_config": asdict(db_config),
            "timestamp": datetime.now().isoformat(),
            "results_directory": str(self.results_dir),
            "run_id": self.run_id,
        }

        config_path = Path(self.results_dir) / "experiment_config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, indent=2)

        logger.info(f"Experiment configuration saved to {config_path}")

    def run(self):
        """Run evolution with parallel job queue."""
        max_jobs = self.evo_config.max_parallel_jobs
        target_gens = self.evo_config.num_generations
        logger.info(
            f"Starting evolution with {max_jobs} parallel jobs, "
            f"target: {target_gens} generations"
        )

        # Log evolution run start to ClickHouse
        try:
            from genesis.utils.clickhouse_logger import ch_logger
            import json

            # Convert configs to JSON-serializable dicts
            def make_serializable(obj):
                """Convert dataclass/OmegaConf objects to JSON-serializable dicts."""
                if hasattr(obj, "__dict__"):
                    obj_dict = (
                        obj.__dict__ if not hasattr(obj, "asdict") else asdict(obj)
                    )
                else:
                    obj_dict = asdict(obj)
                # Convert any remaining OmegaConf objects
                return json.loads(json.dumps(obj_dict, default=str))

            config_dict = {
                "evolution": make_serializable(self.evo_config),
                "database": make_serializable(self.db_config),
                "job": make_serializable(self.job_config),
            }

            # Extract task name from results directory or use unknown
            task_name = "unknown"
            if self.results_dir:
                # Try to extract from path like "results/genesis_squeeze_hnsw/..."
                parts = str(self.results_dir).split("/")
                if len(parts) >= 2:
                    task_name = parts[-2]  # Get the task directory name

            ch_logger.log_evolution_run(
                run_id=self.run_id,
                task_name=task_name,
                config=config_dict,
                population_size=target_gens,  # This will be updated per generation
                cluster_type=self.evo_config.job_type,
                database_path=str(self.results_dir),
                status="running",
            )
        except Exception as e:
            logger.warning(f"Failed to log evolution run start to ClickHouse: {e}")

        # First, run generation 0 sequentially to populate the database
        if self.completed_generations == 0 and target_gens > 0:
            logger.info("Running generation 0 sequentially to initialize database...")
            self._run_generation_0()
            self.completed_generations = 1
            self.next_generation_to_submit = 1
            logger.info(f"Completed generation 0, total: 1/{target_gens}")

        # Now start parallel execution for remaining generations
        if self.completed_generations < target_gens:
            logger.info("Starting parallel execution for remaining generations...")

            # Main loop: monitor jobs and submit new ones
            while (
                self.completed_generations < target_gens or len(self.running_jobs) > 0
            ):
                # Check for completed jobs
                completed_jobs = self._check_completed_jobs()

                # Process completed jobs
                if completed_jobs:
                    for job in completed_jobs:
                        self._process_completed_job(job)

                    # Update completed generations count
                    self._update_completed_generations()

                    if self.verbose:
                        logger.info(
                            f"Processed {len(completed_jobs)} jobs. "
                            f"Total completed generations: "
                            f"{self.completed_generations}/{target_gens}"
                        )

                # Check if we've completed all generations
                if self.completed_generations >= target_gens:
                    logger.info("All generations completed, exiting...")
                    break

                # Submit new jobs to fill the queue (only if we have capacity)
                if (
                    len(self.running_jobs) < max_jobs
                    and self.next_generation_to_submit < target_gens
                ):
                    self._submit_new_job()

                # Wait a bit before checking again
                time.sleep(2)

            # All jobs are now handled by the main loop above

        # Perform final meta summary for any remaining unprocessed programs
        best_program = self.db.get_best_program()
        self.meta_summarizer.perform_final_summary(str(self.results_dir), best_program)

        # Save final meta memory state
        self._save_meta_memory()
        self._save_alma_memory()
        self._save_gepa_state()

        self.db.print_summary()
        logger.info(f"Evolution completed! {self.completed_generations} generations")
        logger.info("=" * 80)
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Evolution run ended at {end_time}")
        logger.info("=" * 80)

        # Update evolution run status in ClickHouse
        try:
            from genesis.utils.clickhouse_logger import ch_logger

            ch_logger.update_evolution_run(
                run_id=self.run_id,
                status="completed",
                total_generations=self.completed_generations,
            )
        except Exception as e:
            logger.warning(f"Failed to update evolution run in ClickHouse: {e}")

    def generate_initial_program(self):
        """Generate initial program with LLM, with retries."""
        llm_kwargs = self.llm.get_kwargs()

        sys_msg, user_msg = self.prompt_sampler.initial_program_prompt()
        msg_history = []
        total_costs = 0.0

        for attempt in range(self.evo_config.max_patch_attempts):
            response = self.llm.query(
                msg=user_msg,
                system_msg=sys_msg,
                llm_kwargs=llm_kwargs,
                msg_history=msg_history,
            )
            if response is None or response.content is None:
                if self.verbose:
                    logger.info(
                        f"  INITIAL PROGRAM ATTEMPT {attempt + 1}/"
                        f"{self.evo_config.max_patch_attempts} "
                        "FAILURE. Error: LLM response content was None."
                    )
                if attempt < self.evo_config.max_patch_attempts - 1:
                    user_msg = (
                        "The previous response was empty. Please try again "
                        "and provide the full code."
                    )
                    if response and response.new_msg_history:
                        msg_history = response.new_msg_history
                    continue
                else:
                    break

            total_costs += response.cost or 0
            initial_code = extract_between(
                response.content,
                f"```{self.evo_config.language}",
                "```",
                False,
            )

            if initial_code:
                patch_name = extract_between(
                    response.content, "<NAME>", "</NAME>", False
                )
                patch_description = extract_between(
                    response.content, "<DESCRIPTION>", "</DESCRIPTION>", False
                )
                thought = (
                    response.thought
                    if response and hasattr(response, "thought")
                    else ""
                )

                if self.evo_config.language == "python":
                    comment_char = "#"
                else:
                    comment_char = "//"

                initial_code = (
                    f"{comment_char} EVOLVE-BLOCK-START\n"
                    f"{initial_code}\n"
                    f"{comment_char} EVOLVE-BLOCK-END\n"
                )

                if self.verbose:
                    logger.info(
                        f"  INITIAL PROGRAM ATTEMPT {attempt + 1}/"
                        f"{self.evo_config.max_patch_attempts} "
                        "SUCCESS."
                    )
                return initial_code, patch_name, patch_description, total_costs, thought
            else:  # code extraction failed
                if self.verbose:
                    logger.info(
                        f"  INITIAL PROGRAM ATTEMPT {attempt + 1}/"
                        f"{self.evo_config.max_patch_attempts} "
                        "FAILURE. Error: Could not extract code from response."
                    )
                if attempt < self.evo_config.max_patch_attempts - 1:
                    user_msg = (
                        "Could not extract code from your last response. "
                        "Please make sure to enclose the code in "
                        "`<CODE>`...`</CODE>` tags."
                    )
                    msg_history = response.new_msg_history
                else:  # last attempt
                    break

        raise ValueError(
            "LLM failed to generate a valid initial program after "
            f"{self.evo_config.max_patch_attempts} attempts."
        )

    def _run_generation_0(self):
        """Setup and run generation 0 to initialize the database."""
        initial_dir = f"{self.results_dir}/{FOLDER_PREFIX}_0"
        Path(initial_dir).mkdir(parents=True, exist_ok=True)
        exec_fname = f"{initial_dir}/main.{self.lang_ext}"
        results_dir = f"{self.results_dir}/{FOLDER_PREFIX}_0/results"
        Path(results_dir).mkdir(parents=True, exist_ok=True)

        api_costs = 0.0
        patch_name = "initial_program"
        patch_description = "Initial program from file."
        patch_type = "init"
        thought = ""

        if self.evo_config.init_program_path:
            if self.verbose:
                logger.info(
                    f"Copying initial program from {self.evo_config.init_program_path}"
                )
            shutil.copy(self.evo_config.init_program_path, exec_fname)
        else:
            if self.verbose:
                logger.info(
                    "`init_program_path` not provided, "
                    "generating initial program with LLM..."
                )
            initial_code, patch_name, patch_description, api_costs, thought = (
                self.generate_initial_program()
            )
            with open(exec_fname, "w", encoding="utf-8") as f:
                f.write(initial_code)

            if self.verbose:
                logger.info(f"Initial program generated and saved to {exec_fname}")

        # Run the evaluation synchronously
        results, rtime = self.scheduler.run(exec_fname, results_dir)

        code_embedding, e_cost = self.get_code_embedding(exec_fname)

        # Read the evaluated code for database insertion
        try:
            evaluated_code = Path(exec_fname).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read code for job {exec_fname}. Error: {e}")
            evaluated_code = ""

        correct_val = False
        metrics_val = {}
        stdout_log = ""
        stderr_log = ""
        if results:
            correct_val = results.get("correct", {}).get("correct", False)
            metrics_val = results.get("metrics", {})
            stdout_log = results.get("stdout_log", "")
            stderr_log = results.get("stderr_log", "")

        combined_score = metrics_val.get("combined_score", 0.0)
        public_metrics = metrics_val.get("public", {})
        private_metrics = metrics_val.get("private", {})
        text_feedback = metrics_val.get("text_feedback", "")

        # Add the program to the database
        db_program = Program(
            id=str(uuid.uuid4()),
            code=evaluated_code,
            language=self.evo_config.language,
            parent_id=None,
            generation=0,
            archive_inspiration_ids=[],
            top_k_inspiration_ids=[],
            code_diff=None,
            embedding=code_embedding,
            correct=correct_val,
            combined_score=combined_score,
            public_metrics=public_metrics,
            private_metrics=private_metrics,
            text_feedback=text_feedback,
            thought=thought,
            metadata={
                "compute_time": rtime,
                "api_costs": api_costs,
                "embed_cost": e_cost,
                "novelty_cost": 0.0,  # No novelty cost for generation 0
                "patch_type": patch_type,
                "patch_name": patch_name,
                "patch_description": patch_description,
                "stdout_log": stdout_log,
                "stderr_log": stderr_log,
                "original_run_id": self.run_id,
            },
        )

        self.db.add(db_program, verbose=True)

        # Log initial individual to ClickHouse
        try:
            from genesis.utils.clickhouse_logger import ch_logger
            import hashlib

            code_hash = hashlib.sha256(evaluated_code.encode()).hexdigest()[:16]

            ch_logger.log_individual(
                run_id=self.run_id,
                individual_id=db_program.id,
                generation=0,
                parent_id="",
                mutation_type=patch_type,
                fitness_score=combined_score,
                combined_score=combined_score,
                metrics={"public": public_metrics, "private": private_metrics},
                is_pareto=True,  # Gen 0 always on Pareto
                api_cost=api_costs,
                embed_cost=e_cost,
                novelty_cost=0.0,
                code_hash=code_hash,
                code_size=len(evaluated_code),
            )
        except Exception as e:
            logger.warning(f"Failed to log initial individual to ClickHouse: {e}")

        if self.llm_selection is not None:
            self.llm_selection.set_baseline_score(
                db_program.combined_score if correct_val else 0.0,
            )
        # ClickHouse auto-commits, no save needed
        self._update_best_solution()

        # Add the evaluated program to meta memory tracking
        self.meta_summarizer.add_evaluated_program(db_program)
        self.alma_memory.observe_outcome(
            generation=job.generation,
            parent_score=parent_score,
            child_score=combined_score,
            correct=correct_val,
            patch_type=job.meta_patch_data.get("patch_type", "")
            if job.meta_patch_data
            else "",
            patch_name=job.meta_patch_data.get("patch_name", "")
            if job.meta_patch_data
            else "",
            patch_description=job.meta_patch_data.get("patch_description", "")
            if job.meta_patch_data
            else "",
            diff_summary=job.meta_patch_data.get("diff_summary", {})
            if job.meta_patch_data
            else {},
            text_feedback=text_feedback,
            error_message=job.meta_patch_data.get("error_attempt")
            if job.meta_patch_data
            else "",
        )

        # Check if we should update meta memory after adding this program
        if self.meta_summarizer.should_update_meta(self.evo_config.meta_rec_interval):
            logger.info(
                f"Updating meta memory after processing "
                f"{len(self.meta_summarizer.evaluated_since_last_meta)} programs..."
            )
            best_program = self.db.get_best_program()
            updated_recs, meta_cost = self.meta_summarizer.update_meta_memory(
                best_program
            )
            if updated_recs:
                # Write meta output file for generation 0
                self.meta_summarizer.write_meta_output(str(self.results_dir))
                # Store meta cost for tracking
                if meta_cost > 0:
                    logger.info(
                        f"Meta recommendation generation cost: ${meta_cost:.4f}"
                    )
                    # Add meta cost to this program's metadata (the one that triggered the update)
                    if db_program.metadata is None:
                        db_program.metadata = {}
                    db_program.metadata["meta_cost"] = meta_cost
                    # Update the program in the database with the new metadata
                    self.db._update_program_metadata(db_program.id, db_program.metadata)

        # Save meta memory state after each job completion
        self._save_meta_memory()
        self._save_gepa_state()

    def _update_completed_generations(self):
        """
        Update the count of completed generations from the database.
        A generation `g` is considered complete if all generations from 0..g
        have at least one program in the database FOR THIS RUN.
        """
        try:
            # Get max generation for this run
            query = f"SELECT max(generation) FROM programs WHERE JSONExtractString(metadata, 'original_run_id') = '{self.run_id}'"
            res = self.db.client.command(query)
            # If no programs, res might be None or 0 depending on CH version/driver
            # Usually None if table empty, but max() on empty set?
            # Let's assume exception or 0.
            last_gen = int(res) if res is not None else -1
        except Exception as e:
            # logger.warning(f"Failed to get max generation: {e}")
            last_gen = -1

        if last_gen == -1:
            self.completed_generations = 0
            # Don't reset next_generation_to_submit here if it was already set higher
            return

        # Check for contiguous generations from 0 up to last_gen
        completed_up_to = 0
        for i in range(last_gen + 1):
            # Check if generation i exists for this run
            try:
                count_query = f"SELECT count() FROM programs WHERE generation = {i} AND JSONExtractString(metadata, 'original_run_id') = '{self.run_id}'"
                count = self.db.client.command(count_query)
            except:
                count = 0

            if count > 0:
                completed_up_to = i + 1

                # Log this generation to ClickHouse if not already logged
                if i not in self.logged_generations:
                    try:
                        prog_query = f"SELECT * FROM programs WHERE generation = {i} AND JSONExtractString(metadata, 'original_run_id') = '{self.run_id}'"
                        prog_res = self.db.client.query(prog_query)
                        if prog_res.result_rows:
                            programs = [
                                self.db._program_from_dict(
                                    dict(zip(prog_res.column_names, row))
                                )
                                for row in prog_res.result_rows
                            ]
                            self._log_generation_to_clickhouse(i, programs)
                            self.logged_generations.add(i)

                            # Recompute clusters periodically (e.g. every 5 gens or last gen)
                            if i % 5 == 0 or i == self.evo_config.num_generations - 1:
                                self.db._recompute_embeddings_and_clusters()
                    except Exception as e:
                        logger.warning(f"Failed to log/process generation {i}: {e}")
            else:
                # Found a gap, so contiguous sequence is broken
                self.completed_generations = completed_up_to
                self.next_generation_to_submit = max(
                    self.next_generation_to_submit, completed_up_to
                )
                return

        self.completed_generations = completed_up_to
        self.next_generation_to_submit = max(
            self.next_generation_to_submit, completed_up_to
        )

    def _log_generation_to_clickhouse(self, generation: int, programs: List[Program]):
        """Log generation statistics and Pareto front to ClickHouse."""
        try:
            from genesis.utils.clickhouse_logger import ch_logger

            # Calculate generation stats
            scores = [p.combined_score for p in programs]
            best_score = max(scores) if scores else 0.0
            avg_score = sum(scores) / len(scores) if scores else 0.0

            # Calculate total costs for this generation
            total_cost = 0.0
            for p in programs:
                if p.metadata:
                    total_cost += p.metadata.get("api_costs", 0.0)
                    total_cost += p.metadata.get("embed_cost", 0.0)
                    total_cost += p.metadata.get("novelty_cost", 0.0)
                    total_cost += p.metadata.get("meta_cost", 0.0)

            # Get Pareto frontier (correct programs only)
            correct_programs = [p for p in programs if p.correct]
            pareto_programs = self._compute_pareto_frontier(correct_programs)
            pareto_size = len(pareto_programs)

            # Log generation stats
            ch_logger.log_generation(
                run_id=self.run_id,
                generation=generation,
                num_individuals=len(programs),
                best_score=best_score,
                avg_score=avg_score,
                pareto_size=pareto_size,
                total_cost=total_cost,
                metadata={
                    "correct_count": len(correct_programs),
                    "incorrect_count": len(programs) - len(correct_programs),
                },
            )

            # Log Pareto frontier
            if pareto_programs:
                pareto_data = []
                for p in pareto_programs:
                    pareto_data.append(
                        {
                            "individual_id": p.id,
                            "fitness_score": p.combined_score,
                            "combined_score": p.combined_score,
                            "metrics": {
                                "public": p.public_metrics or {},
                                "private": p.private_metrics or {},
                            },
                        }
                    )

                ch_logger.log_pareto_front(
                    run_id=self.run_id,
                    generation=generation,
                    pareto_individuals=pareto_data,
                )

        except Exception as e:
            logger.warning(f"Failed to log generation {generation} to ClickHouse: {e}")

    def _compute_pareto_frontier(self, programs: List[Program]) -> List[Program]:
        """Simple Pareto frontier computation based on combined_score (single objective)."""
        if not programs:
            return []

        # For single-objective, just return all programs (or top N)
        # In multi-objective case, you'd compute non-dominated set
        # For now, return all correct programs as they're all potentially "Pareto-optimal"
        return programs

    def _submit_new_job(self):
        """Submit a new job to the queue."""
        current_gen = self.next_generation_to_submit

        if current_gen >= self.evo_config.num_generations:
            return

        self.next_generation_to_submit += 1

        exec_fname = (
            f"{self.results_dir}/{FOLDER_PREFIX}_{current_gen}/main.{self.lang_ext}"
        )
        results_dir = f"{self.results_dir}/{FOLDER_PREFIX}_{current_gen}/results"
        Path(results_dir).mkdir(parents=True, exist_ok=True)

        # Get current meta-recommendations for this job
        meta_recs, meta_summary, meta_scratch = self.meta_summarizer.get_current()

        # Sample parent and inspiration programs
        if current_gen == 0:
            parent_id = None
            archive_insp_ids = []
            top_k_insp_ids = []
            code_diff = None
            meta_patch_data = {}
            # Initial program already copied in setup_initial_program
        else:
            api_costs = 0
            embed_cost = 0
            novelty_cost = 0.0
            novelty_checks_performed = 0
            # Loop over novelty attempts
            for nov_attempt in range(self.evo_config.max_novelty_attempts):
                # Loop over patch resamples - including parents
                for resample in range(self.evo_config.max_patch_resamples):
                    (
                        parent_program,
                        archive_programs,
                        top_k_programs,
                    ) = self.db.sample(
                        target_generation=current_gen,
                        novelty_attempt=nov_attempt + 1,
                        max_novelty_attempts=self.evo_config.max_novelty_attempts,
                        resample_attempt=resample + 1,
                        max_resample_attempts=self.evo_config.max_patch_resamples,
                    )
                    archive_insp_ids = [p.id for p in archive_programs]
                    top_k_insp_ids = [p.id for p in top_k_programs]
                    parent_id = parent_program.id
                    # Run patch (until success with max attempts)
                    code_diff, meta_patch_data, num_applied_attempt = self.run_patch(
                        parent_program,
                        archive_programs,
                        top_k_programs,
                        current_gen,
                        novelty_attempt=nov_attempt + 1,
                        resample_attempt=resample + 1,
                    )
                    api_costs += meta_patch_data["api_costs"]
                    if (
                        meta_patch_data["error_attempt"] is None
                        and num_applied_attempt > 0
                    ):
                        meta_patch_data["api_costs"] = api_costs
                        break

                # Get the code embedding for the evaluated code
                code_embedding, e_cost = self.get_code_embedding(exec_fname)
                embed_cost += e_cost

                if not code_embedding:
                    self.novelty_judge.log_novelty_skip_message("no embedding")
                    break

                # Use NoveltyJudge for novelty assessment with rejection sampling
                if self.novelty_judge.should_check_novelty(
                    code_embedding, current_gen, parent_program, self.db
                ):
                    should_accept, novelty_metadata = (
                        self.novelty_judge.assess_novelty_with_rejection_sampling(
                            exec_fname, code_embedding, parent_program, self.db
                        )
                    )

                    # Update costs and metadata from novelty assessment
                    novelty_cost += novelty_metadata.get("novelty_total_cost", 0.0)
                    novelty_checks_performed = novelty_metadata.get(
                        "novelty_checks_performed", 0
                    )
                    novelty_explanation = novelty_metadata.get(
                        "novelty_explanation", ""
                    )

                    if should_accept:
                        break
                    # If not accepted, continue to next attempt (rejection sampling)
                else:
                    if not self.db.island_manager or not hasattr(
                        self.db.island_manager, "are_all_islands_initialized"
                    ):
                        self.novelty_judge.log_novelty_skip_message("no island manager")
                    elif not self.db.island_manager.are_all_islands_initialized():
                        self.novelty_judge.log_novelty_skip_message(
                            "not all islands initialized yet"
                        )
                    break

        # Add meta-recommendations/summary/scratchpad to meta_patch_data
        if meta_recs is not None:
            meta_patch_data["meta_recommendations"] = meta_recs
            meta_patch_data["meta_summary"] = meta_summary
            meta_patch_data["meta_scratch_pad"] = meta_scratch

        # Add novelty check information to meta_patch_data if any checks were performed
        if current_gen > 0 and novelty_checks_performed > 0:
            meta_patch_data["novelty_checks_performed"] = novelty_checks_performed
            meta_patch_data["novelty_cost"] = novelty_cost
            meta_patch_data["novelty_explanation"] = novelty_explanation

        # Submit the job asynchronously
        job_id = self.scheduler.submit_async(exec_fname, results_dir)

        # Add to running jobs queue
        running_job = RunningJob(
            job_id=job_id,
            exec_fname=exec_fname,
            results_dir=results_dir,
            start_time=time.time(),
            generation=current_gen,
            parent_id=parent_id,
            archive_insp_ids=archive_insp_ids,
            top_k_insp_ids=top_k_insp_ids,
            code_diff=code_diff,
            meta_patch_data=meta_patch_data,
            code_embedding=code_embedding,
            embed_cost=embed_cost,
            novelty_cost=novelty_cost,
        )
        self.running_jobs.append(running_job)

        if self.verbose:
            logger.info(
                f"Submitted job for generation {current_gen}, "
                f"queue size: {len(self.running_jobs)}"
            )

        # ClickHouse Log
        try:
            from genesis.utils.clickhouse_logger import ch_logger

            ch_logger.log_action(
                action_type="job_submitted",
                details={
                    "job_id": str(job_id),
                    "generation": current_gen,
                    "parent_id": parent_id,
                    "exec_fname": exec_fname,
                },
                metadata=meta_patch_data,
            )
        except Exception as e:
            logger.warning(f"Failed to log job submission to ClickHouse: {e}")

    def _check_completed_jobs(self) -> List[RunningJob]:
        """Check for completed jobs and return them."""
        completed = []
        still_running = []

        for job in self.running_jobs:
            is_running = self.scheduler.check_job_status(job)
            if not is_running:
                # Job completed
                if self.verbose:
                    logger.info(f"Job {job.job_id} completed!")
                completed.append(job)
            else:
                # Job still running
                still_running.append(job)

        self.running_jobs = still_running
        return completed

    def _process_completed_job(self, job: RunningJob):
        """Process a completed job and add results to database."""
        end_time = time.time()
        rtime = end_time - job.start_time

        # Get job results
        results = self.scheduler.get_job_results(job.job_id, job.results_dir)

        # Read the evaluated code
        try:
            evaluated_code = Path(job.exec_fname).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read code for job {job.job_id}. Error: {e}")
            evaluated_code = ""

        # Use pre-computed embedding and novelty costs
        code_embedding = job.code_embedding
        e_cost = job.embed_cost
        n_cost = job.novelty_cost
        if self.verbose:
            logger.debug(
                f"=> Using pre-computed embedding for job {job.job_id}, "
                f"embed cost: {e_cost:.4f}, novelty cost: {n_cost:.4f}"
            )

        correct_val = False
        metrics_val = {}
        stdout_log = ""
        stderr_log = ""
        if results:
            correct_val = results.get("correct", {}).get("correct", False)
            metrics_val = results.get("metrics", {})
            stdout_log = results.get("stdout_log", "")
            stderr_log = results.get("stderr_log", "")

        combined_score = metrics_val.get("combined_score", 0.0)
        public_metrics = metrics_val.get("public", {})
        private_metrics = metrics_val.get("private", {})
        text_feedback = metrics_val.get("text_feedback", "")
        parent_program = self.db.get(job.parent_id) if job.parent_id else None
        parent_score = parent_program.combined_score if parent_program else 0.0

        # Add the program to the database
        db_program = Program(
            id=str(uuid.uuid4()),
            code=evaluated_code,
            language=self.evo_config.language,
            parent_id=job.parent_id,
            generation=job.generation,
            archive_inspiration_ids=job.archive_insp_ids,
            top_k_inspiration_ids=job.top_k_insp_ids,
            code_diff=job.code_diff,
            embedding=code_embedding,
            correct=correct_val,
            combined_score=combined_score,
            public_metrics=public_metrics,
            private_metrics=private_metrics,
            text_feedback=text_feedback,
            thought=job.meta_patch_data.get("thought", "")
            if job.meta_patch_data
            else "",
            metadata={
                "compute_time": rtime,
                **(job.meta_patch_data or {}),
                "embed_cost": e_cost,
                "novelty_cost": n_cost,
                "stdout_log": stdout_log,
                "stderr_log": stderr_log,
                "original_run_id": self.run_id,
            },
        )
        self.db.add(db_program, verbose=True)

        self.gepa_optimizer.observe_result(
            generation=job.generation,
            parent_score=parent_score,
            child_score=combined_score,
            patch_type=job.meta_patch_data.get("patch_type", "")
            if job.meta_patch_data
            else "",
            patch_name=job.meta_patch_data.get("patch_name", "")
            if job.meta_patch_data
            else "",
            patch_description=job.meta_patch_data.get("patch_description", "")
            if job.meta_patch_data
            else "",
            diff_summary=job.meta_patch_data.get("diff_summary", {})
            if job.meta_patch_data
            else {},
            candidate_id=job.meta_patch_data.get("gepa_candidate_id")
            if job.meta_patch_data
            else None,
            correct=correct_val,
        )
        self.alma_memory.observe_outcome(
            generation=job.generation,
            parent_score=parent_score,
            child_score=combined_score,
            correct=correct_val,
            patch_type=job.meta_patch_data.get("patch_type", "")
            if job.meta_patch_data
            else "",
            patch_name=job.meta_patch_data.get("patch_name", "")
            if job.meta_patch_data
            else "",
            patch_description=job.meta_patch_data.get("patch_description", "")
            if job.meta_patch_data
            else "",
            diff_summary=job.meta_patch_data.get("diff_summary", {})
            if job.meta_patch_data
            else {},
            text_feedback=text_feedback,
            error_message=job.meta_patch_data.get("error_attempt")
            if job.meta_patch_data
            else "",
        )

        # Log individual to ClickHouse
        try:
            from genesis.utils.clickhouse_logger import ch_logger
            import hashlib

            # Compute code hash
            code_hash = hashlib.sha256(evaluated_code.encode()).hexdigest()[:16]

            # Get parent program for fitness delta
            fitness_delta = combined_score - parent_score

            # Determine mutation type from metadata
            mutation_type = (
                job.meta_patch_data.get("patch_type", "unknown")
                if job.meta_patch_data
                else "unknown"
            )

            # Check if on Pareto frontier (will be updated later if needed)
            is_pareto = False  # Will be set properly when Pareto is computed

            ch_logger.log_individual(
                run_id=self.run_id,
                individual_id=db_program.id,
                generation=job.generation,
                parent_id=job.parent_id or "",
                mutation_type=mutation_type,
                fitness_score=combined_score,
                combined_score=combined_score,
                metrics={"public": public_metrics, "private": private_metrics},
                is_pareto=is_pareto,
                api_cost=job.meta_patch_data.get("api_costs", 0.0)
                if job.meta_patch_data
                else 0.0,
                embed_cost=e_cost,
                novelty_cost=n_cost,
                code_hash=code_hash,
                code_size=len(evaluated_code),
            )

            # Log lineage if has parent
            if job.parent_id:
                edit_summary = (
                    job.meta_patch_data.get("patch_description", "")
                    if job.meta_patch_data
                    else ""
                )
                ch_logger.log_lineage(
                    run_id=self.run_id,
                    child_id=db_program.id,
                    parent_id=job.parent_id,
                    generation=job.generation,
                    mutation_type=mutation_type,
                    fitness_delta=fitness_delta,
                    edit_summary=edit_summary[:500],  # Truncate to reasonable length
                )
        except Exception as e:
            logger.warning(f"Failed to log individual/lineage to ClickHouse: {e}")

        # Add the evaluated program to meta memory tracking
        self.meta_summarizer.add_evaluated_program(db_program)

        # Check if we should update meta memory after adding this program
        if self.meta_summarizer.should_update_meta(self.evo_config.meta_rec_interval):
            logger.info(
                f"Updating meta memory after processing "
                f"{len(self.meta_summarizer.evaluated_since_last_meta)} programs..."
            )
            best_program = self.db.get_best_program()
            updated_recs, meta_cost = self.meta_summarizer.update_meta_memory(
                best_program
            )
            if updated_recs:
                # Write meta output file using accumulated program count
                self.meta_summarizer.write_meta_output(str(self.results_dir))
                # Store meta cost for tracking
                if meta_cost > 0:
                    logger.info(
                        f"Meta recommendation generation cost: ${meta_cost:.4f}"
                    )
                    # Add meta cost to this program's metadata (the one that triggered the update)
                    if db_program.metadata is None:
                        db_program.metadata = {}
                    db_program.metadata["meta_cost"] = meta_cost
                    # Update the program in the database with the new metadata
                    self.db._update_program_metadata(db_program.id, db_program.metadata)

        if self.llm_selection is not None:
            if "model_name" not in db_program.metadata:
                logger.warning(
                    "No model_name found in program metadata, "
                    "unable to update model selection algorithm."
                )
            else:
                parent = (
                    self.db.get(db_program.parent_id) if db_program.parent_id else None
                )
                baseline = parent.combined_score if parent else None
                reward = db_program.combined_score if correct_val else None
                model_name = db_program.metadata["model_name"]
                result = self.llm_selection.update(
                    arm=model_name,
                    reward=reward,
                    baseline=baseline,
                )
                if result and self.verbose:
                    normalized_score, baseline = result

                    def fmt(x):
                        return f"{x:.4f}" if isinstance(x, (float, int)) else "None"

                    logger.debug(
                        f"==> UPDATED LLM SELECTION: model: "
                        f"{model_name.split('/')[-1][-25:]}..., "
                        f"score: {fmt(normalized_score)}, "
                        f"raw score: {fmt(reward)}, baseline: {fmt(baseline)}"
                    )
                    self.llm_selection.print_summary()

        # ClickHouse auto-commits, no save needed
        self._update_best_solution()

        # ClickHouse Log
        try:
            from genesis.utils.clickhouse_logger import ch_logger

            ch_logger.log_action(
                action_type="job_completed",
                details={
                    "job_id": str(job.job_id),
                    "generation": job.generation,
                    "correct": correct_val,
                    "combined_score": combined_score,
                    "api_costs": job.meta_patch_data.get("api_costs", 0)
                    if job.meta_patch_data
                    else 0,
                    "embed_cost": job.embed_cost,
                    "novelty_cost": job.novelty_cost,
                },
                metadata={
                    "public_metrics": public_metrics,
                    "private_metrics": private_metrics,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to log job completion to ClickHouse: {e}")

        # Note: Meta summarization check is now done after completed generations
        # are updated in the main loop to ensure correct timing

        # Save meta memory state after each job completion
        self._save_meta_memory()
        self._save_alma_memory()
        self._save_gepa_state()

    def _update_best_solution(self):
        """Checks and updates the best program."""
        best_programs = self.db.get_top_programs(n=1, correct_only=True)
        if not best_programs:
            if self.verbose:
                logger.debug(
                    "No correct programs found yet, cannot determine best solution."
                )
            return

        best_program = best_programs[0]

        if best_program.id == self.best_program_id:
            return  # No change

        self.best_program_id = best_program.id

        source_dir = (
            Path(self.results_dir) / f"{FOLDER_PREFIX}_{best_program.generation}"
        )
        best_dir = Path(self.results_dir) / "best"

        if best_dir.exists():
            shutil.rmtree(best_dir)

        if source_dir.exists():
            shutil.copytree(source_dir, best_dir)
        else:
            logger.warning(f"Source directory does not exist: {source_dir}")

        if self.verbose:
            logger.info(
                f"New best program found: gen {best_program.generation}, "
                f"id {best_program.id[:6]}... "
                f"Copied to {best_dir}"
            )

    def run_patch(
        self,
        parent_program: Program,
        archive_programs: List[Program],
        top_k_programs: List[Program],
        generation: int,
        novelty_attempt: int = 1,
        resample_attempt: int = 1,
    ) -> tuple[Optional[str], dict, int]:
        """Run patch generation for a specific generation."""
        max_patch_attempts = self.evo_config.max_patch_attempts
        if self.verbose:
            logger.info(
                f"Edit Cycle {generation} -> {generation + 1}, "
                f"Max Patch Attempts: {max_patch_attempts}"
            )
        # Get current meta recommendations
        meta_recs, _, _ = self.meta_summarizer.get_current()
        alma_context = self.alma_memory.build_prompt_context(
            current_generation=generation,
            parent_code=parent_program.code,
            parent_feedback=parent_program.text_feedback
            if isinstance(parent_program.text_feedback, str)
            else "",
        )
        gepa_ctx = self.gepa_optimizer.build_prompt_context()
        # Construct edit / code change message
        patch_sys, patch_msg, patch_type = self.prompt_sampler.sample(
            parent=parent_program,
            archive_inspirations=archive_programs,
            top_k_inspirations=top_k_programs,
            meta_recommendations=meta_recs,
            alma_memory_context=alma_context,
            gepa_instruction=gepa_ctx["candidate_instruction"],
            gepa_fewshot_examples=gepa_ctx["fewshot_examples"],
        )

        if patch_type in ["full", "cross"]:
            apply_patch = apply_full_patch
        elif patch_type == "diff":
            apply_patch = apply_diff_patch
        elif patch_type == "paper":
            raise NotImplementedError("Paper edit not implemented.")
            # apply_patch = apply_paper_patch
        else:
            raise ValueError(f"Invalid patch type: {patch_type}")

        total_costs = 0
        msg_history = []
        llm_kwargs = self.llm.get_kwargs()
        if self.llm_selection is not None:
            model_name = llm_kwargs["model_name"]
            self.llm_selection.update_submitted(model_name)
        code_diff = None  # Initialize code_diff
        num_applied_attempt = 0  # Initialize num_applied_attempt
        error_attempt = (
            "Max attempts reached without successful patch."  # Default error
        )
        patch_name = None
        patch_description = None
        output_path_attempt = None
        patch_txt_attempt = None
        patch_path = None
        diff_summary = {}

        # Configure web search tool
        tools = None
        tool_map = None
        if self.evo_config.web_search_enabled:
            # Check if we should use search for this attempt (probabilistic)
            # Or just enable it and let the model decide?
            # User said "at least occasionally". Let's use the probability to enable the tool availability.
            import random

            if random.random() < self.evo_config.web_search_prob:
                if self.verbose:
                    logger.info("Web search enabled for this patch attempt.")

                tools = [
                    {
                        "name": "search_web",
                        "description": "Search the web for information, documentation, or code snippets. Use this when you need external knowledge to solve the problem.",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "The search query",
                                },
                                "num_results": {
                                    "type": "integer",
                                    "description": "Number of results to return (default 5)",
                                    "default": 5,
                                },
                            },
                            "required": ["query"],
                        },
                    }
                ]
                tool_map = {"search_web": search_web}

        for patch_attempt in range(max_patch_attempts):
            response = self.llm.query(
                msg=patch_msg,
                system_msg=patch_sys,
                msg_history=msg_history,
                llm_kwargs=llm_kwargs,
            )
            # print(response.content)
            if response is None or response.content is None:
                if self.verbose:
                    logger.info(
                        f"  PATCH ATTEMPT {patch_attempt + 1}/{max_patch_attempts} FAILURE. "
                        f"Error: LLM response content was None."
                    )
                # Prepare for next attempt or exit
                error_attempt = "LLM response content was None."
                num_applied_attempt = 0
                patch_txt_attempt = None
                if patch_attempt < max_patch_attempts - 1:
                    patch_msg = (
                        "The previous attempt to get an edit was not "
                        "successful because the LLM response was empty. "
                        "Try again."
                    )
                    if response:
                        msg_history = response.new_msg_history
                    continue
                else:  # Last attempt
                    break

            total_costs += response.cost  # Acc. cost
            patch_name = extract_between(
                response.content,
                "<NAME>",
                "</NAME>",
                False,
            )
            patch_description = extract_between(
                response.content,
                "<DESCRIPTION>",
                "</DESCRIPTION>",
                False,
            )

            # Apply the code patch (diff/full rewrite)
            (
                _,
                num_applied_attempt,
                output_path_attempt,
                error_attempt,
                patch_txt_attempt,
                patch_path,
            ) = apply_patch(
                original_str=parent_program.code,
                patch_str=response.content,
                patch_dir=f"{self.results_dir}/{FOLDER_PREFIX}_{generation}",
                language=self.evo_config.language,
                verbose=False,
            )

            # Check for validation errors if patch was successfully applied
            if (
                error_attempt is None
                and num_applied_attempt > 0
                and output_path_attempt
            ):
                validation_error = self._validate_code(
                    str(output_path_attempt), self.evo_config.language
                )
                if validation_error:
                    error_attempt = f"Code validation failed:\n{validation_error}"
                    if self.verbose:
                        logger.info(
                            f"  PATCH ATTEMPT {patch_attempt + 1}/{max_patch_attempts} "
                            f"VALIDATION FAILURE.\n{validation_error}"
                        )
                    # Reset success indicators so it retries
                    num_applied_attempt = 0
                    output_path_attempt = None
                    # IMPORTANT: Revert or cleanup?
                    # The file was written to output_path_attempt (main.rs).
                    # The next attempt will overwrite it, so explicit cleanup isn't strictly necessary,
                    # but good practice if we want to leave "failed" artifacts for inspection?
                    # For now, we leave it, as the next successful apply will overwrite.

            if error_attempt is None and num_applied_attempt > 0:
                if patch_path:  # Ensure patch_path is not None
                    diff_summary = summarize_diff(
                        str(patch_path)
                    )  # Convert Path to str
                if self.verbose:
                    logger.info(
                        f"  PATCH ATTEMPT {patch_attempt + 1}/{max_patch_attempts} SUCCESS. "
                        f"Output: {output_path_attempt}, "
                        f"Patches Applied: {num_applied_attempt}."
                    )

                code_diff = patch_txt_attempt
                break  # Break from patch attempts
            else:
                error_str = (
                    str(error_attempt) if error_attempt else "No changes applied."
                )
                patch_msg = (
                    "The previous edit was not successful."
                    + " This was the error message: \n\n"
                    + error_str
                    + "\n\n Try again."
                )
                if self.verbose:
                    logger.info(
                        f"  PATCH ATTEMPT {patch_attempt + 1}/{max_patch_attempts} FAILURE. "
                        f"Error: '{error_str}', "
                        f"Patches Applied: {num_applied_attempt}."
                    )
                msg_history = response.new_msg_history
                code_diff = None
                if patch_attempt == max_patch_attempts - 1:  # Last attempt failed
                    # error_attempt is already set from apply_patch or default
                    pass

        # Only consider the diff summary for the original source file
        original_filename = f"original.{self.lang_ext}"
        if original_filename in diff_summary:
            diff_summary = diff_summary[original_filename]

        meta_edit_data = {
            "patch_type": patch_type,
            "api_costs": total_costs,
            "num_applied": num_applied_attempt,
            "patch_name": patch_name,
            "patch_description": patch_description,
            "error_attempt": error_attempt,
            "novelty_attempt": novelty_attempt,
            "resample_attempt": resample_attempt,
            "patch_attempt": patch_attempt + 1,
            **llm_kwargs,
            "llm_result": response.to_dict() if response else None,
            "diff_summary": diff_summary,
            "thought": response.thought
            if response and hasattr(response, "thought")
            else "",
            "gepa_candidate_id": gepa_ctx["candidate_id"],
            "gepa_candidate_instruction": gepa_ctx["candidate_instruction"],
        }
        if self.verbose and num_applied_attempt > 0:
            self._print_metadata_table(meta_edit_data, generation)
        # Delete generation from meta_edit_data
        return code_diff, meta_edit_data, num_applied_attempt

    def _validate_code(self, file_path: str, language: str) -> Optional[str]:
        """
        Validate the generated code using language-specific tools.
        Returns None if valid, or an error message string if invalid.
        """
        import subprocess

        try:
            if language == "rust":
                # Try compiling with rustc to check for errors
                # -Z no-codegen is faster as it only checks analysis
                # But -Z requires nightly. Let's stick to standard rustc which is fast enough for small files.
                # Use --crate-type lib to avoid main function requirement if it's a library,
                # but our programs usually have main or are standalone.
                # "initial.rs" suggests a standalone file.
                cmd = ["rustc", "--crate-type", "bin", "-o", "/dev/null", file_path]

                # Check if clippy is available and preferred?
                # The user mentioned "cargo clippy --pedantic".
                # If there is no Cargo.toml, clippy might be hard to invoke on a single file without setup.
                # But we can try rustc first.

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    # Filter output to keep it concise?
                    return result.stderr.strip()

            elif language == "python":
                # Check syntax
                cmd = ["python3", "-m", "py_compile", file_path]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    return result.stderr.strip()

            # Add other languages as needed

        except subprocess.TimeoutExpired:
            return "Validation timed out."
        except Exception as e:
            return f"Validation execution failed: {e}"

        return None

    def get_code_embedding(self, exec_fname: str) -> tuple[List[float], float]:
        """Get the embedding of the code."""
        # Read the evaluated code
        try:
            evaluated_code = Path(exec_fname).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not read code for job {exec_fname}. Error: {e}")
            evaluated_code = ""
        if evaluated_code != "":
            # Get the embedding of the initial program
            try:
                if self.embedding is not None:
                    redacted_code = redact_immutable(evaluated_code, no_state=True)
                    if self.verbose:
                        logger.debug(
                            "=> EMBED: Code length - "
                            f"Original: {len(evaluated_code)} - "
                            f"Redacted: {len(redacted_code)}"
                        )

                    embedding_result, e_cost = self.embedding.get_embedding(
                        redacted_code
                    )
                else:
                    if self.verbose:
                        logger.debug("=> EMBED: No embedding model configured.")
                    embedding_result = []
                    e_cost = 0.0
                code_embedding = cast(List[float], embedding_result)
            except Exception as e:
                logger.warning(f"Could not embed code for job {exec_fname}. Error: {e}")
                code_embedding = []
                e_cost = 0.0
        else:
            code_embedding = []
            e_cost = 0.0
        return code_embedding, e_cost

    def _print_metadata_table(self, meta_data: dict, generation: int):
        """Display metadata in a formatted rich table."""
        # Create title with generation and attempt information
        title_parts = ["[bold magenta]Patch Metadata"]

        # Add generation if present
        if generation is not None:
            title_parts.append(
                f" - Gen {generation}/{self.evo_config.num_generations} - Novelty: {meta_data['novelty_attempt']}/{self.evo_config.max_novelty_attempts} - Resample: {meta_data['resample_attempt']}/{self.evo_config.max_patch_resamples} - Patch: {meta_data['patch_attempt']}/{self.evo_config.max_patch_attempts}"
            )

        # Add attempt information if present
        if all(
            key in meta_data
            for key in [
                "novelty_attempt",
                "resample_attempt",
                "patch_attempt",
                "generation",
            ]
        ):
            title_parts.append(
                f" (Novelty: {meta_data['novelty_attempt']}, "
                f"Resample: {meta_data['resample_attempt']}, "
                f"Patch: {meta_data['patch_attempt']})"
            )

        title_parts.append("[/bold magenta]")
        table = Table(
            title="".join(title_parts),
            show_header=True,
            header_style="bold cyan",
            border_style="magenta",
            box=rich.box.ROUNDED,
            width=120,  # Match display.py table width
        )
        table.add_column("Field", style="cyan bold", no_wrap=True, width=25)
        table.add_column("Value", style="green", overflow="fold", width=90)

        # Define display order and formatting for specific fields
        display_order = [
            "patch_type",
            "patch_name",
            "patch_description",
            "num_applied",
            "api_costs",
            "error_attempt",
        ]

        # Add ordered fields first
        for field_name in display_order:
            if field_name in meta_data:
                value = meta_data[field_name]
                if value is None:
                    formatted_value = "[dim]None[/dim]"
                elif field_name == "api_costs":
                    formatted_value = f"${value:.4f}"
                elif field_name == "error_attempt" and value is None:
                    formatted_value = "[green]Success[/green]"
                elif field_name == "error_attempt":
                    formatted_value = (
                        f"[red]{str(value)[:100]}...[/red]"
                        if len(str(value)) > 100
                        else f"[red]{value}[/red]"
                    )
                else:
                    formatted_value = str(value)

                table.add_row(field_name, formatted_value)

        # Add remaining fields (excluding llm_result, diff_summary, and header info)
        skip_fields = set(
            display_order
            + [
                "llm_result",
                "diff_summary",
                "generation",
                "novelty_attempt",
                "resample_attempt",
                "patch_attempt",
            ]
        )
        for field_key, field_value in meta_data.items():
            if field_key not in skip_fields:
                if field_value is None:
                    formatted_value = "[dim]None[/dim]"
                else:
                    formatted_value = (
                        str(field_value)[:100] + "..."
                        if len(str(field_value)) > 100
                        else str(field_value)
                    )
                table.add_row(field_key, formatted_value)

        # Add diff summary if available
        if "diff_summary" in meta_data and meta_data["diff_summary"]:
            diff_summary = meta_data["diff_summary"]
            if isinstance(diff_summary, dict):
                summary_text = ""
                for k, v in diff_summary.items():
                    summary_text += f"{k}: {v}; "
                table.add_row("diff_summary", summary_text.strip())
            else:
                table.add_row("diff_summary", str(diff_summary)[:200])

        self.console.print(table)

    def _save_meta_memory(self) -> None:
        """Save the meta memory state to disk."""
        meta_memory_path = Path(self.results_dir) / "meta_memory.json"
        self.meta_summarizer.save_meta_state(str(meta_memory_path))

    def _save_alma_memory(self) -> None:
        """Save ALMA memory state to disk."""
        if not self.evo_config.alma_enabled:
            return
        alma_memory_path = Path(self.results_dir) / "alma_memory.json"
        self.alma_memory.save_state(str(alma_memory_path))

    def _save_gepa_state(self) -> None:
        """Save GEPA optimizer state to disk."""
        if not self.evo_config.gepa_enabled:
            return
        gepa_state_path = Path(self.results_dir) / "gepa_state.json"
        self.gepa_optimizer.save_state(str(gepa_state_path))

    def _restore_meta_memory(self) -> None:
        """Restore the meta memory state from disk."""
        meta_memory_path = Path(self.results_dir) / "meta_memory.json"

        if self.verbose:
            logger.info(f"Attempting to restore meta memory from: {meta_memory_path}")

        success = self.meta_summarizer.load_meta_state(str(meta_memory_path))
        if success:
            logger.info("Successfully restored meta memory state")
        else:
            if meta_memory_path.exists():
                logger.warning(
                    f"Meta memory file exists but failed to load: {meta_memory_path}"
                )
            else:
                logger.info("No previous meta memory state found - starting fresh")

    def _restore_alma_memory(self) -> None:
        """Restore ALMA memory state from disk."""
        if not self.evo_config.alma_enabled:
            return
        alma_memory_path = Path(self.results_dir) / "alma_memory.json"
        success = self.alma_memory.load_state(str(alma_memory_path))
        if success:
            logger.info(f"Restored ALMA memory from {alma_memory_path}")

    def _restore_gepa_state(self) -> None:
        """Restore GEPA optimizer state from disk."""
        if not self.evo_config.gepa_enabled:
            return
        gepa_state_path = Path(self.results_dir) / "gepa_state.json"
        success = self.gepa_optimizer.load_state(str(gepa_state_path))
        if success:
            logger.info(f"Restored GEPA state from {gepa_state_path}")
