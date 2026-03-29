# SAGA-Inspired Modular Architecture for Genesis

## Overview

This document proposes a modular refactoring of Genesis's architecture to align with SAGA's four-module design (Planner, Implementer, Optimizer, Analyzer). This refactoring would improve code maintainability, extensibility, and research reproducibility.

**Related**: See [`saga_integration.md`](saga_integration.md) for the broader SAGA integration strategy.

---

## Current Architecture Analysis

### EvolutionRunner: The 1756-Line Monolith

The `EvolutionRunner` class (`genesis/core/runner.py`) currently handles:

1. **Configuration Management** (lines ~100-200)
   - Initialize evolution parameters
   - Set up job scheduler, database, LLM clients

2. **Solution Search** (lines ~300-900)
   - Parent selection
   - Prompt construction
   - LLM querying
   - Patch application
   - Job submission

3. **Population Management** (lines ~900-1200)
   - Island model maintenance
   - Archive updates
   - Migration logic

4. **Meta-Level Analysis** (lines ~1200-1500)
   - Trigger meta-summarizer
   - Process recommendations

5. **Evaluation Orchestration** (lines ~1500-1700)
   - Collect job results
   - Update database
   - Track best programs

**Problems**:
- ❌ All concerns mixed together
- ❌ Hard to test individual components
- ❌ Difficult to swap out algorithms (e.g., try Bayesian optimization instead of evolution)
- ❌ Tight coupling makes research experiments cumbersome

---

## SAGA Four-Module Architecture

### 1. Planner Module

**Responsibility**: Strategic planning and objective decomposition

**Current Genesis Component**: `task_sys_msg` + `MetaSummarizer` (partial)

**Proposed Interface**:

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from dataclasses import dataclass

@dataclass
class Objective:
    """Represents a single optimization objective."""
    name: str
    description: str
    weight: float
    higher_is_better: bool

@dataclass
class Plan:
    """High-level optimization plan."""
    objectives: List[Objective]
    strategy: str  # "explore" | "exploit" | "balanced"
    recommended_iterations: int
    notes: str

class PlannerInterface(ABC):
    """Plans optimization strategy and objectives."""

    @abstractmethod
    def create_initial_plan(self, task_description: str) -> Plan:
        """Create initial optimization plan from task description."""

    @abstractmethod
    def update_plan(
        self,
        current_plan: Plan,
        population_analysis: "AnalysisResult",
        generation: int
    ) -> Optional[Plan]:
        """Update plan based on evolution progress.

        Returns None if no update needed, or new Plan if changes required.
        """

    @abstractmethod
    def should_continue(
        self,
        current_plan: Plan,
        generation: int,
        best_score: float
    ) -> bool:
        """Determine if evolution should continue."""
```

**Default Implementation**:

```python
class StaticPlanner(PlannerInterface):
    """Default planner using static task_sys_msg (current Genesis behavior)."""

    def __init__(self, task_sys_msg: str, num_generations: int):
        self.task_sys_msg = task_sys_msg
        self.num_generations = num_generations

    def create_initial_plan(self, task_description: str) -> Plan:
        return Plan(
            objectives=[Objective("combined_score", "User-defined fitness", 1.0, True)],
            strategy="balanced",
            recommended_iterations=self.num_generations,
            notes=f"Static plan from task_sys_msg: {self.task_sys_msg[:100]}..."
        )

    def update_plan(self, current_plan, population_analysis, generation):
        return None  # No dynamic updates

    def should_continue(self, current_plan, generation, best_score):
        return generation < self.num_generations
```

**SAGA-Inspired Implementation**:

```python
class ObjectiveEvolvingPlanner(PlannerInterface):
    """Planner that evolves objectives dynamically (SAGA-style)."""

    def __init__(
        self,
        llm_client: LLMClient,
        base_metrics: List[str],
        evolution_interval: int = 50
    ):
        self.llm_client = llm_client
        self.base_metrics = base_metrics
        self.evolution_interval = evolution_interval
        self.evolution_history: List[Plan] = []

    def create_initial_plan(self, task_description: str) -> Plan:
        # Use LLM to decompose task into objectives
        response = self.llm_client.query(
            system_msg="You are an expert at decomposing optimization tasks...",
            user_msg=f"Task: {task_description}\nMetrics: {self.base_metrics}\n..."
        )
        # Parse response into objectives with initial weights
        return Plan(objectives=..., strategy="explore", ...)

    def update_plan(self, current_plan, population_analysis, generation):
        if generation % self.evolution_interval != 0:
            return None

        # Analyze if objectives need updating
        if population_analysis.reward_hacking_detected:
            # Use LLM to propose new objective weights
            new_objectives = self._evolve_objectives(current_plan, population_analysis)
            return Plan(objectives=new_objectives, ...)
        return None

    def _evolve_objectives(self, plan, analysis):
        # LLM-driven objective evolution logic
        ...
```

---

### 2. Implementer Module

**Responsibility**: Generate code mutations and apply patches

**Current Genesis Component**: `PromptSampler` + `LLMClient` + `edit/*`

**Proposed Interface**:

```python
@dataclass
class CodeMutation:
    """Represents a code modification."""
    parent_id: str
    mutation_type: str  # "diff" | "full" | "crossover"
    code_content: str
    patch: Optional[str]  # For diff patches
    llm_cost: float
    metadata: Dict

class ImplementerInterface(ABC):
    """Generates code mutations."""

    @abstractmethod
    def generate_mutation(
        self,
        parent_program: Program,
        inspirations: List[Program],
        task_context: str,
        meta_recommendations: Optional[str] = None
    ) -> CodeMutation:
        """Generate a code mutation from parent program."""

    @abstractmethod
    def apply_mutation(
        self,
        base_code: str,
        mutation: CodeMutation
    ) -> Tuple[str, bool]:
        """Apply mutation to base code.

        Returns (new_code, success).
        """
```

**Default Implementation**:

```python
class LLMImplementer(ImplementerInterface):
    """Current Genesis implementation using LLM mutations."""

    def __init__(
        self,
        llm_client: LLMClient,
        sampler: PromptSampler,
        patch_types: List[str],
        max_attempts: int = 5
    ):
        self.llm_client = llm_client
        self.sampler = sampler
        self.patch_types = patch_types
        self.max_attempts = max_attempts

    def generate_mutation(self, parent_program, inspirations, task_context, meta_recs):
        # Current PromptSampler logic
        patch_type = random.choice(self.patch_types)
        prompt = self.sampler.construct_prompt(
            parent=parent_program,
            inspirations=inspirations,
            patch_type=patch_type,
            task_context=task_context,
            meta_recommendations=meta_recs
        )
        response = self.llm_client.query(**prompt)
        return CodeMutation(
            parent_id=parent_program.id,
            mutation_type=patch_type,
            code_content=extract_code(response),
            ...
        )

    def apply_mutation(self, base_code, mutation):
        if mutation.mutation_type == "diff":
            return apply_diff_patch(base_code, mutation.patch)
        elif mutation.mutation_type == "full":
            return apply_full_patch(base_code, mutation.code_content)
        # ...
```

---

### 3. Optimizer Module

**Responsibility**: Select candidates for mutation and manage solution search

**Current Genesis Component**: `EvolutionRunner` + `islands.py` + `parents.py`

**Proposed Interface**:

```python
@dataclass
class Population:
    """Represents current population state."""
    programs: List[Program]
    islands: List[List[Program]]
    archive: List[Program]
    generation: int

class OptimizerInterface(ABC):
    """Manages solution search strategy."""

    @abstractmethod
    def select_parents(
        self,
        population: Population,
        num_parents: int
    ) -> List[Program]:
        """Select programs to mutate next."""

    @abstractmethod
    def update_population(
        self,
        population: Population,
        new_programs: List[Program]
    ) -> Population:
        """Update population with new evaluated programs."""

    @abstractmethod
    def should_migrate(self, generation: int) -> bool:
        """Determine if island migration should occur."""

    @abstractmethod
    def perform_migration(self, population: Population) -> Population:
        """Perform island migration."""
```

**Default Implementation**:

```python
class IslandEvolutionOptimizer(OptimizerInterface):
    """Current Genesis island model + evolutionary search."""

    def __init__(
        self,
        num_islands: int,
        selection_strategy: str,
        archive_size: int,
        migration_interval: int
    ):
        self.num_islands = num_islands
        self.selection_strategy = selection_strategy
        self.archive_size = archive_size
        self.migration_interval = migration_interval

    def select_parents(self, population, num_parents):
        # Current parent selection logic
        # Power-law, weighted, or beam search
        ...

    def update_population(self, population, new_programs):
        # Add to islands
        # Update archive
        # Maintain diversity
        ...

    def should_migrate(self, generation):
        return generation % self.migration_interval == 0

    def perform_migration(self, population):
        # Current migration logic
        ...
```

**Alternative Implementations**:

```python
class BayesianOptimizer(OptimizerInterface):
    """Bayesian optimization over code space using embeddings."""

    def __init__(self, embedding_client: EmbeddingClient):
        self.gp_model = GaussianProcessRegressor()
        self.embedding_client = embedding_client

    def select_parents(self, population, num_parents):
        # Use acquisition function (e.g., UCB) to select promising areas
        embeddings = [self.embedding_client.embed(p.code) for p in population.programs]
        scores = [p.combined_score for p in population.programs]

        # Fit GP model
        self.gp_model.fit(embeddings, scores)

        # Select parents in unexplored high-potential regions
        candidates = self._generate_candidates(population)
        ucb_scores = self._compute_ucb(candidates)
        return self._select_top_k(candidates, ucb_scores, num_parents)

class MCTSOptimizer(OptimizerInterface):
    """Monte Carlo Tree Search over code mutation space."""

    def __init__(self, exploration_constant: float = 1.414):
        self.tree = MCTSTree()
        self.c = exploration_constant

    def select_parents(self, population, num_parents):
        # Tree search to find promising mutations
        # Each node is a program, edges are mutations
        for _ in range(num_parents):
            leaf = self.tree.select(self.c)  # UCB selection
            self.tree.expand(leaf)
        return self.tree.get_best_leaves(num_parents)
```

---

### 4. Analyzer Module

**Responsibility**: Evaluate solutions and provide feedback

**Current Genesis Component**: `MetaSummarizer` + `evaluate.py` + database queries

**Proposed Interface**:

```python
@dataclass
class AnalysisResult:
    """Results of population analysis."""
    summary: str
    recommendations: List[str]
    reward_hacking_detected: bool
    convergence_status: str  # "exploring" | "converging" | "converged"
    key_insights: List[str]
    objective_quality_score: float  # How well current objectives capture true goal

class AnalyzerInterface(ABC):
    """Analyzes population and provides insights."""

    @abstractmethod
    def analyze_population(
        self,
        population: Population,
        plan: Plan
    ) -> AnalysisResult:
        """Analyze current population state."""

    @abstractmethod
    def analyze_program(
        self,
        program: Program,
        evaluation_results: Dict
    ) -> Dict:
        """Analyze individual program evaluation."""

    @abstractmethod
    def detect_reward_hacking(
        self,
        programs: List[Program],
        objectives: List[Objective]
    ) -> Tuple[bool, str]:
        """Detect if high scores come from exploits.

        Returns (is_hacking, explanation).
        """
```

**Default Implementation**:

```python
class MetaAnalyzer(AnalyzerInterface):
    """Current MetaSummarizer with enhanced objective analysis."""

    def __init__(
        self,
        llm_client: LLMClient,
        use_text_feedback: bool = False,
        max_recommendations: int = 5
    ):
        self.llm_client = llm_client
        self.use_text_feedback = use_text_feedback
        self.max_recommendations = max_recommendations
        self.meta_summary = None
        self.meta_recommendations = None

    def analyze_population(self, population, plan):
        # Current 3-step meta-analysis
        step1 = self._analyze_programs(population.programs)
        step2 = self._synthesize_insights(step1)
        step3 = self._generate_recommendations(step2)

        # NEW: Objective quality analysis
        hacking_detected, explanation = self.detect_reward_hacking(
            population.programs,
            plan.objectives
        )

        return AnalysisResult(
            summary=step2,
            recommendations=step3,
            reward_hacking_detected=hacking_detected,
            convergence_status=self._assess_convergence(population),
            key_insights=self._extract_insights(step1, step2),
            objective_quality_score=self._score_objectives(population, plan)
        )

    def detect_reward_hacking(self, programs, objectives):
        if len(objectives) == 1:
            return False, "Single objective - no multi-objective hacking possible"

        # Analyze if high-scoring programs have suspicious metric patterns
        top_programs = sorted(programs, key=lambda p: p.combined_score, reverse=True)[:10]

        prompt = OBJECTIVE_HACKING_DETECTION_PROMPT.format(
            programs=[{m: p.raw_metrics.get(m, 0) for m in objectives} for p in top_programs],
            objectives={o.name: o.weight for o in objectives}
        )

        response = self.llm_client.query(system_msg=..., user_msg=prompt)

        # Parse LLM response
        result = json.loads(response)
        return result['hacking_detected'], result['explanation']
```

---

## Refactored EvolutionRunner

After extracting modules, `EvolutionRunner` becomes a slim orchestrator:

```python
class EvolutionRunner:
    """Orchestrates evolution using modular components."""

    def __init__(
        self,
        planner: PlannerInterface,
        implementer: ImplementerInterface,
        optimizer: OptimizerInterface,
        analyzer: AnalyzerInterface,
        database: ProgramDatabase,
        scheduler: JobScheduler,
        config: EvolutionConfig
    ):
        self.planner = planner
        self.implementer = implementer
        self.optimizer = optimizer
        self.analyzer = analyzer
        self.database = database
        self.scheduler = scheduler
        self.config = config

        # State
        self.current_plan: Optional[Plan] = None
        self.current_population: Optional[Population] = None

    def run(self):
        """Main evolution loop - now < 100 lines!"""

        # Initialize
        self.current_plan = self.planner.create_initial_plan(self.config.task_sys_msg)
        self.current_population = self._initialize_population()

        for generation in range(self.config.num_generations):
            # Check if we should continue
            if not self.planner.should_continue(self.current_plan, generation, self._get_best_score()):
                break

            # Select parents
            parents = self.optimizer.select_parents(self.current_population, self.config.max_parallel_jobs)

            # Generate mutations
            mutations = []
            for parent in parents:
                inspirations = self._get_inspirations(parent)
                mutation = self.implementer.generate_mutation(
                    parent,
                    inspirations,
                    self.current_plan.objectives,
                    self.current_plan.notes
                )
                mutations.append(mutation)

            # Evaluate mutations (submit jobs)
            new_programs = self._evaluate_mutations(mutations)

            # Update population
            self.current_population = self.optimizer.update_population(
                self.current_population,
                new_programs
            )

            # Analyze population
            analysis = self.analyzer.analyze_population(self.current_population, self.current_plan)

            # Update plan if needed
            new_plan = self.planner.update_plan(self.current_plan, analysis, generation)
            if new_plan:
                self._handle_plan_update(new_plan, analysis)
                self.current_plan = new_plan

            # Migrate islands if needed
            if self.optimizer.should_migrate(generation):
                self.current_population = self.optimizer.perform_migration(self.current_population)

            # Log progress
            self._log_generation(generation, analysis)

    def _evaluate_mutations(self, mutations: List[CodeMutation]) -> List[Program]:
        """Submit jobs and wait for results."""
        # Job scheduling logic (still needed but isolated)
        ...

    def _handle_plan_update(self, new_plan: Plan, analysis: AnalysisResult):
        """Handle objective evolution."""
        logger.info(f"Plan updated: {analysis.summary}")
        # Re-score population if objectives changed
        ...
```

**Benefits**:
- EvolutionRunner shrinks from 1756 lines to ~200 lines
- Core loop is crystal clear
- Easy to test each module independently
- Can swap out components (e.g., try MCTSOptimizer)

---

## Configuration with Modules

### Hydra Config Structure

```yaml
# configs/planner/static.yaml
_target_: genesis.core.modules.StaticPlanner
task_sys_msg: ${task.task_sys_msg}
num_generations: ${evolution.num_generations}

# configs/planner/objective_evolving.yaml
_target_: genesis.core.modules.ObjectiveEvolvingPlanner
base_metrics: ${task.base_metrics}
evolution_interval: 50

# configs/implementer/llm.yaml
_target_: genesis.core.modules.LLMImplementer
patch_types: ${evolution.patch_types}
max_attempts: ${evolution.max_patch_attempts}

# configs/optimizer/island_evolution.yaml
_target_: genesis.core.modules.IslandEvolutionOptimizer
num_islands: ${database.num_islands}
selection_strategy: power_law
archive_size: ${database.archive_size}
migration_interval: 10

# configs/optimizer/bayesian.yaml
_target_: genesis.core.modules.BayesianOptimizer
acquisition_function: ucb
embedding_model: ${evolution.embedding_model}

# configs/optimizer/mcts.yaml
_target_: genesis.core.modules.MCTSOptimizer
exploration_constant: 1.414
rollout_budget: 100

# configs/analyzer/meta.yaml
_target_: genesis.core.modules.MetaAnalyzer
use_text_feedback: ${evolution.use_text_feedback}
max_recommendations: ${evolution.meta_max_recommendations}
```

### Usage

```yaml
# configs/variant/saga_bayesian.yaml
defaults:
  - /task@_here_: circle_packing
  - /planner@_here_: objective_evolving
  - /implementer@_here_: llm
  - /optimizer@_here_: bayesian
  - /analyzer@_here_: meta

evolution:
  num_generations: 100
```

**Run**:
```bash
genesis_launch variant=saga_bayesian
```

---

## Migration Path

### Phase 1: Create Interfaces (Week 1)

**Goal**: Define module interfaces without breaking existing code

- [ ] Create `genesis/core/interfaces.py`
- [ ] Define PlannerInterface, ImplementerInterface, OptimizerInterface, AnalyzerInterface
- [ ] Write docstrings and type hints

### Phase 2: Implement Default Modules (Week 2-3)

**Goal**: Extract current logic into module implementations

- [ ] Implement `StaticPlanner` (wraps current task_sys_msg)
- [ ] Implement `LLMImplementer` (wraps current PromptSampler + patch logic)
- [ ] Implement `IslandEvolutionOptimizer` (wraps current island model)
- [ ] Implement `MetaAnalyzer` (wraps current MetaSummarizer)

**Note**: At this stage, behavior should be 100% identical to current Genesis.

### Phase 3: Refactor EvolutionRunner (Week 4)

**Goal**: Make EvolutionRunner use modules via interfaces

- [ ] Modify `EvolutionRunner.__init__` to accept module instances
- [ ] Refactor main loop to delegate to modules
- [ ] Add factory function to create modules from config (backward compatibility)

```python
def create_evolution_runner_from_config(config: EvolutionConfig) -> EvolutionRunner:
    """Factory for backward compatibility."""
    planner = StaticPlanner(config.task_sys_msg, config.num_generations)
    implementer = LLMImplementer(...)
    optimizer = IslandEvolutionOptimizer(...)
    analyzer = MetaAnalyzer(...)

    return EvolutionRunner(planner, implementer, optimizer, analyzer, ...)
```

**Test**: All existing examples should run identically.

### Phase 4: Hydra Integration (Week 5)

**Goal**: Enable module selection via Hydra configs

- [ ] Create config groups for each module type
- [ ] Test config composition
- [ ] Update documentation

### Phase 5: Alternative Implementations (Week 6+)

**Goal**: Demonstrate extensibility with new modules

- [ ] Implement `ObjectiveEvolvingPlanner`
- [ ] Implement `BayesianOptimizer`
- [ ] Create examples showcasing alternatives
- [ ] Benchmark: Evolution vs Bayesian vs MCTS

---

## Benefits

### For Users

1. **Easier Experimentation**: Swap out components via config
   ```yaml
   # Try different optimizers without code changes
   optimizer: bayesian  # vs island_evolution, mcts
   ```

2. **Better Debugging**: Isolated modules easier to debug
   ```python
   # Test implementer in isolation
   implementer = LLMImplementer(...)
   mutation = implementer.generate_mutation(parent, inspirations, ...)
   ```

3. **Clearer Logs**: Each module can have dedicated logging
   ```
   [Planner] Objective evolution triggered: reward hacking detected
   [Optimizer] Island migration performed: 20 programs exchanged
   [Analyzer] Convergence detected: top 5 programs within 1% of each other
   ```

### For Researchers

1. **Reproducible Experiments**: Module configuration fully specifies behavior
2. **Fair Comparisons**: Same implementer + analyzer, different optimizers
3. **Easy to Extend**: Add new module type without touching core
4. **Publication-Ready**: "We use IslandEvolutionOptimizer from Genesis with ObjectiveEvolvingPlanner..."

### For Developers

1. **Testability**: Each module has clear inputs/outputs
2. **Maintainability**: 200-line modules vs 1756-line monolith
3. **Code Review**: Changes scoped to specific modules
4. **Parallel Development**: Teams can work on different modules

---

## Example: Swapping Optimizers

### Current (Without Modularity)

To try Bayesian optimization instead of evolution:
1. Fork `EvolutionRunner`
2. Modify internal logic (lines 300-900)
3. Hope you didn't break something else
4. Hard to compare fairly with original

### With Modular Architecture

```python
# bayesian_optimizer.py (new file, 150 lines)
class BayesianOptimizer(OptimizerInterface):
    def select_parents(self, population, num_parents):
        # Bayesian optimization logic
        ...

# Config change only!
# configs/optimizer/bayesian.yaml
_target_: genesis.core.modules.BayesianOptimizer
acquisition_function: ucb
```

**Run**:
```bash
# Baseline
genesis_launch task=circle_packing optimizer=island_evolution

# Experiment
genesis_launch task=circle_packing optimizer=bayesian

# Compare results
genesis_compare exp1 exp2 --metric combined_score --plot
```

---

## Testing Strategy

### Unit Tests

Each module gets dedicated tests:

```python
# tests/core/test_implementer.py
def test_llm_implementer_diff_mutation():
    parent = Program(code="def foo(): return 1")
    inspirations = []
    implementer = LLMImplementer(mock_llm_client, ...)

    mutation = implementer.generate_mutation(parent, inspirations, ...)

    assert mutation.mutation_type == "diff"
    assert mutation.parent_id == parent.id

# tests/core/test_optimizer.py
def test_island_evolution_parent_selection():
    population = create_test_population(50)
    optimizer = IslandEvolutionOptimizer(num_islands=4, ...)

    parents = optimizer.select_parents(population, num_parents=10)

    assert len(parents) == 10
    # Verify power-law distribution
```

### Integration Tests

Full end-to-end with mocked components:

```python
def test_evolution_runner_with_mock_modules():
    planner = MockPlanner()
    implementer = MockImplementer()
    optimizer = MockOptimizer()
    analyzer = MockAnalyzer()

    runner = EvolutionRunner(planner, implementer, optimizer, analyzer, ...)
    runner.run()

    # Verify modules called correctly
    assert planner.update_plan.call_count == 10  # Called every generation
    assert implementer.generate_mutation.call_count == 100  # 10 gens * 10 parallel
```

### Regression Tests

Ensure refactoring doesn't change behavior:

```python
def test_backward_compatibility():
    """Verify default modules produce same results as pre-refactoring."""
    # Run with old EvolutionRunner (pre-refactoring)
    old_results = run_evolution_old(...)

    # Run with new modular EvolutionRunner (default modules)
    new_results = run_evolution_new(...)

    # Should be identical
    assert old_results.best_score == new_results.best_score
    assert old_results.num_evaluations == new_results.num_evaluations
```

---

## Comparison with Other Frameworks

### FunSearch (DeepMind)

**Architecture**:
- Evaluator: Runs programs and scores them
- Sampler: LLM generates new programs
- Database: Stores programs

**Comparison**:
- ✅ Similar to Genesis: Evaluator ≈ our Analyzer, Sampler ≈ our Implementer
- ❌ No explicit Planner or Optimizer modules
- ❌ Less modular than SAGA design

### AlphaEvolve (DeepMind)

**Architecture** (based on paper):
- Ensemble LLM: Gemini Flash + Pro
- Island-based population
- Fitness evaluator

**Comparison**:
- ✅ Similar island model to our IslandEvolutionOptimizer
- ✅ Multi-LLM support (Genesis already has this)
- ❌ No objective evolution or planning

### ShinkaEvolve (Sakana AI)

**Architecture**:
- Parent sampler (adaptive)
- Novelty judge
- Meta-summarizer
- Bandit-based LLM selection

**Comparison**:
- ✅ Genesis is forked from ShinkaEvolve - same foundation
- ✅ This modular refactoring makes Genesis more extensible than ShinkaEvolve
- ✅ SAGA integration (Planner + objective evolution) would be novel contribution

---

## Open Questions

### 1. Module Communication

**Question**: How should modules share state?

**Options**:
- A) Pass everything explicitly (functional style)
  ```python
  population = optimizer.update_population(population, new_programs)
  ```
  - ✅ Clear data flow
  - ❌ Verbose

- B) Shared state object
  ```python
  class EvolutionState:
      population: Population
      plan: Plan
      analysis: AnalysisResult
  ```
  - ✅ Less passing around
  - ❌ Mutable state harder to track

**Recommendation**: Option A for now (explicit is better than implicit).

### 2. Backward Compatibility

**Question**: Should old `EvolutionRunner` API be deprecated immediately?

**Recommendation**:
- Keep old API for 1-2 releases with deprecation warning
- Provide migration script: `python scripts/migrate_to_modular.py`
- Document migration in `docs/migration_guide.md`

### 3. Performance Overhead

**Question**: Does modular design add overhead (extra function calls, etc.)?

**Answer**: Negligible compared to LLM query time (seconds) and program evaluation (seconds/minutes). Module abstraction cost is microseconds.

**Benchmark**:
```python
# Test: 1000 parent selections
old_time = benchmark(old_evolution_runner.select_parents, 1000)
new_time = benchmark(new_optimizer.select_parents, 1000)

# Expected: new_time ≈ old_time (< 1% difference)
```

---

## Related Documentation

- [SAGA Integration Overview](saga_integration.md)
- [Evolution Approach](evolutionary_approach.md)
- [Configuration Reference](configuration.md)
- [Developer Guide](developer_guide.md)

---

## Implementation Checklist

**Phase 1: Interfaces** (Week 1)
- [ ] Create `genesis/core/interfaces.py`
- [ ] Define all four module interfaces
- [ ] Write comprehensive docstrings
- [ ] Add type hints

**Phase 2: Default Implementations** (Weeks 2-3)
- [ ] Implement StaticPlanner
- [ ] Implement LLMImplementer
- [ ] Implement IslandEvolutionOptimizer
- [ ] Implement MetaAnalyzer
- [ ] Unit tests for each module

**Phase 3: Refactor EvolutionRunner** (Week 4)
- [ ] Modify EvolutionRunner to use modules
- [ ] Create factory function for backward compatibility
- [ ] Regression tests (ensure same behavior)
- [ ] Update existing examples

**Phase 4: Hydra Integration** (Week 5)
- [ ] Create config groups for each module type
- [ ] Test config composition
- [ ] Update documentation
- [ ] Migration guide

**Phase 5: Alternative Implementations** (Weeks 6-8)
- [ ] Implement ObjectiveEvolvingPlanner
- [ ] Implement BayesianOptimizer
- [ ] Implement MCTSOptimizer
- [ ] Create examples showcasing alternatives
- [ ] Benchmark comparisons

**Phase 6: Documentation & Release** (Week 9)
- [ ] Complete this document
- [ ] Tutorial: "Creating Custom Modules"
- [ ] Blog post: "Genesis Goes Modular"
- [ ] Release notes

---

## Conclusion

Modular architecture brings Genesis in line with modern software engineering practices and research frameworks like SAGA. The investment in refactoring pays dividends in:

- Maintainability
- Extensibility
- Testability
- Research reproducibility
- User customization

**Next Steps**:
1. Review this proposal with team
2. Prototype Phase 1 (interfaces) in separate branch
3. Validate design with simple example
4. Proceed with full implementation

The combination of **modular architecture** (this document) + **objective evolution** (from SAGA) would make Genesis the most advanced open-source LLM-driven code evolution framework.
