# SAGA Framework Integration Notes

## Overview

This document explores how concepts from the SAGA (Self-Adapting Goal-Evolving Agents) paper could enhance Genesis's evolutionary code optimization capabilities.

**Paper**: [SAGA: Autonomous Goal-Evolving Agents for Scientific Discovery](https://arxiv.org/html/2512.21782v1)

**Key Insight**: While Genesis excels at evolving code (solution optimization), SAGA introduces a complementary outer loop that evolves the *objectives themselves* (goal evolution). This bi-level optimization prevents reward hacking and enables more sophisticated scientific discovery.

---

## SAGA Paper Summary

### Core Contributions

**1. Bi-Level Optimization Architecture**
- **Inner Loop** (Solution Optimization): Search for programs that maximize current objectives
- **Outer Loop** (Objective Evolution): Refine objectives based on intermediate results and failure analysis

**2. Four Agentic Modules**
- **Planner**: Decomposes high-level scientific goals into measurable objectives
- **Implementer**: Converts objectives into executable scoring functions
- **Optimizer**: Searches for solutions that optimize current scoring functions
- **Analyzer**: Evaluates results and identifies when objectives need refinement

**3. Three Autonomy Levels**
- **Co-pilot**: Human provides guidance at each step
- **Semi-pilot**: Human reviews analysis and approves objective changes
- **Autopilot**: Fully autonomous operation

**4. Domain-Agnostic Success**
Demonstrated across antibiotic design, materials science, DNA design, and chemical engineering.

### Key Innovation: Dynamic Objective Evolution

Traditional approaches use **fixed fitness functions** that can lead to:
- **Reward hacking**: Solutions exploit loopholes in the objective
- **Local optima**: Single objective misses multi-dimensional trade-offs
- **Specification drift**: Initial objectives don't capture true goals

SAGA addresses this by **evolving objectives**:
1. Detect when high scores come from exploits vs true optimization
2. Analyze failure modes and missing constraints
3. Propose refined objectives that better capture scientific goals
4. Iterate until objectives align with true discovery needs

---

## Genesis ↔ SAGA Module Mapping

Genesis already implements components similar to SAGA's four modules, but with different emphases:

| SAGA Module | Genesis Component | Match Quality | Notes |
|-------------|------------------|---------------|-------|
| **Planner** | `task_sys_msg` + `MetaSummarizer` (partial) | 40% | Genesis has strategic guidance but no explicit goal decomposition |
| **Implementer** | `PromptSampler` + `LLMClient` + `edit/*` | 70% | Strong code generation and mutation capabilities |
| **Optimizer** | `EvolutionRunner` + `islands.py` + `novelty_judge.py` | 50% | Robust solution search, but optimization is implicit in evolution loop |
| **Analyzer** | `MetaSummarizer` + `evaluate.py` | 60% | Population analysis exists, but limited feedback to objective-level planning |

### Detailed Component Mapping

#### SAGA Planner → Genesis Components

**SAGA Planner**:
- Decomposes scientific goals into specific, measurable objectives
- Identifies competing trade-offs (e.g., efficacy vs toxicity)
- Proposes objective functions to optimize

**Genesis Equivalent**:
- `task_sys_msg`: High-level task description for LLM mutations
- `MetaSummarizer` (partial): Provides strategic recommendations

**Gap**: Genesis lacks explicit goal decomposition. Users manually define `evaluate.py`, which remains static throughout evolution.

**SAGA-Inspired Enhancement**:
```python
class ObjectivePlanner:
    """Plans and evolves fitness function objectives."""

    def decompose_goal(self, scientific_goal: str) -> List[Metric]:
        """LLM decomposes high-level goal into measurable metrics."""
        # Example: "Design antibiotics" → [efficacy, toxicity, synthesizability]

    def identify_tradeoffs(self, metrics: List[Metric]) -> Dict[str, float]:
        """Determine initial weighting of competing objectives."""

    def propose_objective_update(
        self,
        population_analysis: str,
        current_objectives: Dict
    ) -> Dict:
        """Suggest refined objectives based on evolution outcomes."""
```

---

#### SAGA Implementer → Genesis Components

**SAGA Implementer**:
- Converts abstract objectives into executable scoring functions
- Generates Python code for fitness evaluation
- Ensures objective functions are differentiable/tractable

**Genesis Equivalent**:
- `PromptSampler`: Constructs LLM prompts for code mutations
- `LLMClient`: Executes LLM queries to generate code
- `edit/apply_diff.py`, `edit/apply_full.py`: Apply code modifications

**Match Quality**: ✅ **70% - Good alignment**

**Analysis**: Genesis's Implementer is strong for *solution-level* code generation (mutating programs). SAGA's Implementer focuses on *objective-level* code generation (creating scoring functions).

**SAGA-Inspired Enhancement**:
Extend Genesis to generate `evaluate.py` dynamically:
```python
# Current: User provides evaluate.py manually
def evaluate(program):
    return combined_score  # Static

# SAGA-inspired: LLM generates evaluate.py based on objectives
class FitnessImplementer:
    def generate_evaluation_function(
        self,
        objectives: List[Metric],
        weights: Dict[str, float]
    ) -> str:
        """Generate Python code for multi-objective evaluation."""
        # Returns new evaluate.py content
```

---

#### SAGA Optimizer → Genesis Components

**SAGA Optimizer**:
- Bayesian optimization, genetic algorithms, or gradient-based search
- Refines candidate solutions to maximize current objectives
- Iterates until convergence or budget exhausted

**Genesis Equivalent**:
- `EvolutionRunner`: Main evolution loop
- `islands.py`: Population management with island model
- `parents.py`: Parent selection strategies
- `inspirations.py`: Archive-based learning
- `novelty_judge.py`: Diversity maintenance

**Match Quality**: ✅ **50% - Moderate alignment**

**Analysis**: Genesis has a sophisticated evolutionary optimizer, but it's tightly coupled with the mutation logic. SAGA's Optimizer is a more modular, swappable component.

**Gap**: Genesis's optimizer is implicit in the evolution loop. No clean interface for plugging in alternative optimizers (e.g., MCTS, Bayesian optimization).

**SAGA-Inspired Enhancement**:
Extract optimizer interface:
```python
class OptimizerBase(ABC):
    @abstractmethod
    def select_parents(self, population: List[Program]) -> List[Program]:
        """Select programs for mutation."""

    @abstractmethod
    def should_continue(self, generation: int, best_score: float) -> bool:
        """Determine if optimization should continue."""

class EvolutionaryOptimizer(OptimizerBase):
    """Current Genesis approach (island model + evolution)."""

class BayesianOptimizer(OptimizerBase):
    """Alternative: Gaussian process-guided search."""

class MCTSOptimizer(OptimizerBase):
    """Alternative: Monte Carlo tree search over code space."""
```

---

#### SAGA Analyzer → Genesis Components

**SAGA Analyzer**:
- Evaluates solution quality across multiple objectives
- Identifies failure modes and reward hacking
- Provides structured feedback to Planner for objective refinement
- Generates insights on why certain solutions succeed/fail

**Genesis Equivalent**:
- `MetaSummarizer`: 3-step LLM-based population analysis
- `evaluate.py`: Executes programs and returns fitness metrics
- `Database.get_best_programs()`: Retrieves top performers

**Match Quality**: ⚠️ **60% - Partial alignment with key gap**

**Analysis**: Genesis analyzes populations well, but primarily for **solution-level insights** (e.g., "try different algorithms"). It doesn't systematically identify **objective-level issues** (e.g., "fitness function rewards wrong behavior").

**Gap**: MetaSummarizer generates recommendations for code mutations, not for objective function changes. No explicit reward hacking detection.

**SAGA-Inspired Enhancement**:
Extend MetaSummarizer with objective analysis:
```python
class EnhancedAnalyzer(MetaSummarizer):
    def analyze_objective_quality(
        self,
        population: List[Program],
        current_objectives: Dict
    ) -> ObjectiveAnalysis:
        """Detect reward hacking and objective misalignment."""
        # Check for patterns like:
        # - High scores from edge cases
        # - Dominance of single objective over others
        # - Solutions missing key constraints

        return ObjectiveAnalysis(
            reward_hacking_detected=True,
            problematic_metric="speed",
            suggested_refinement="Add correctness weight",
            confidence=0.85
        )
```

---

## Current Gaps & Opportunities

### 1. Fixed Objective Functions ⚠️ **Critical Gap**

**Current State**:
- `evaluate.py` is provided by users and remains static
- Returns `combined_score` (single scalar) for fitness ranking
- Multi-objective information (`public` dict) is logged but not used in evolution

**SAGA Approach**:
- Objectives evolve based on population analysis
- Multi-objective Pareto frontier tracking
- Dynamic reweighting when reward hacking detected

**Example Problem**:
```python
# Task: Optimize sorting algorithm
# evaluate.py (initial)
def aggregate_metrics(results):
    execution_time = results[0]['time']
    return {
        "combined_score": 1.0 / execution_time  # Faster = better
    }

# Problem: LLM discovers "reward hack"
def sort(arr):
    return []  # Empty list is instant! High score, but incorrect.
```

**SAGA Solution**:
After detecting high scores with incorrect outputs, evolve the objective:
```python
# evaluate.py (evolved)
def aggregate_metrics(results):
    execution_time = results[0]['time']
    correctness = results[0]['correct']  # NEW: Validate output
    return {
        "combined_score": correctness * (1.0 / execution_time)
    }
```

**Opportunity**: Implement objective evolution as an optional feature in Genesis.

---

### 2. No Explicit Planner for Objective Decomposition

**Current State**:
- Users manually design fitness functions
- No guidance on how to balance competing objectives
- Task description (`task_sys_msg`) focuses on code mutations, not objectives

**SAGA Approach**:
- Planner decomposes high-level goals into specific metrics
- Example: "Design antibiotics" → {efficacy, toxicity, synthesizability, cost}
- Provides initial weights based on domain knowledge

**Opportunity**: Add optional "objective planner" that helps users design better fitness functions upfront.

---

### 3. Limited Human-in-the-Loop (Only at Setup)

**Current State**:
- Genesis runs fully autonomously after initial configuration
- Users can review results via WebUI, but can't intervene during evolution

**SAGA Approach**:
- **Co-pilot**: Human reviews and approves each objective change
- **Semi-pilot**: Human reviews analyzer insights, system auto-evolves
- **Autopilot**: Fully autonomous (similar to current Genesis)

**Opportunity**: Add intervention points where users can:
- Approve/reject objective changes
- Provide feedback on mutation strategies
- Manually inject promising code variants

---

### 4. Single `combined_score` vs Multi-Objective Pareto

**Current State**:
- Evolution ranks programs by single scalar `combined_score`
- `public` metrics are logged but not used for selection
- No Pareto frontier tracking

**SAGA Approach**:
- Maintains Pareto frontier: solutions optimal in different dimensions
- Example: Program A (fast, memory-heavy) vs Program B (slower, memory-efficient)
- Both are "elite" in different objectives

**Opportunity**: Extend Genesis to:
- Track Pareto-optimal programs in archive
- Sample parents from across Pareto frontier
- Visualize trade-offs in WebUI

---

## SAGA-Inspired Implementation Roadmap

### Phase 1: Objective Evolution (High Priority)

**Goal**: Enable dynamic fitness function evolution

**Implementation**:
1. **New Module**: `genesis/core/objective_evolution.py`
   ```python
   class ObjectiveEvolver:
       """Manages dynamic objective function evolution."""

       def __init__(self, llm_client: LLMClient, base_metrics: List[str]):
           self.current_weights = {metric: 1.0 for metric in base_metrics}
           self.evolution_history = []

       def should_evolve(self, generation: int, interval: int) -> bool:
           """Check if objectives should be updated this generation."""

       def analyze_and_evolve(
           self,
           meta_insights: str,
           population_metrics: List[Dict]
       ) -> Dict[str, float]:
           """Detect reward hacking and propose new weights."""
   ```

2. **Extend `EvolutionConfig`** (in `runner.py`):
   ```python
   @dataclass
   class EvolutionConfig:
       # Existing fields...

       # NEW: Objective evolution
       objective_evolution_enabled: bool = False
       objective_evolution_interval: int = 50  # Evolve every N generations
       objective_base_metrics: List[str] = field(default_factory=list)
       objective_evolution_llm_models: Optional[List[str]] = None
   ```

3. **Modify `wrap_eval.py`** to support raw multi-metrics:
   ```python
   # Current: aggregate_metrics_fn must return {'combined_score': float}
   # New: Can return {'metric1': float, 'metric2': float} without combined_score
   # ObjectiveEvolver computes combined_score from weighted sum
   ```

4. **Integration with `MetaSummarizer`**:
   - Extend meta-analysis to detect objective-level issues
   - Add prompts for analyzing reward hacking patterns
   - Feed insights into ObjectiveEvolver

**Example Usage**:
```yaml
# configs/evolution/objective_evolution.yaml
objective_evolution_enabled: true
objective_evolution_interval: 50
objective_base_metrics:
  - execution_time
  - memory_usage
  - correctness
  - code_complexity
```

**Expected Behavior**:
- Generation 0-49: Optimize weighted combination
- Generation 50: ObjectiveEvolver analyzes population
  - Detects: High scores but low correctness
  - Action: Increase correctness weight, decrease speed weight
- Generation 51+: Evolution continues with refined objectives

---

### Phase 2: Modular Architecture (Medium Priority)

**Goal**: Refactor Genesis to align with SAGA's four-module design

**Benefits**:
- Clearer separation of concerns
- Easier to extend (e.g., plug in Bayesian optimizer)
- Better testability
- More intuitive for researchers

**Implementation**:
1. **Define Module Interfaces** (in `genesis/core/interfaces.py`):
   ```python
   class PlannerInterface(ABC):
       @abstractmethod
       def plan_objectives(self, goal: str) -> List[Metric]:
           """Decompose goal into metrics."""

   class ImplementerInterface(ABC):
       @abstractmethod
       def generate_code(self, prompt: str) -> str:
           """Generate code mutation."""

   class OptimizerInterface(ABC):
       @abstractmethod
       def select_next_candidates(self, population: List[Program]) -> List[Program]:
           """Select programs to mutate next."""

   class AnalyzerInterface(ABC):
       @abstractmethod
       def analyze_population(self, programs: List[Program]) -> AnalysisResult:
           """Analyze evolution progress."""
   ```

2. **Refactor `EvolutionRunner`** from 1756-line monolithic class to slim orchestrator:
   ```python
   class EvolutionRunner:
       def __init__(
           self,
           planner: PlannerInterface,
           implementer: ImplementerInterface,
           optimizer: OptimizerInterface,
           analyzer: AnalyzerInterface,
       ):
           self.planner = planner
           self.implementer = implementer
           self.optimizer = optimizer
           self.analyzer = analyzer

       def run_generation(self, generation: int):
           # Thin coordination layer
           candidates = self.optimizer.select_next_candidates(...)
           mutations = self.implementer.generate_code(...)
           analysis = self.analyzer.analyze_population(...)
           # ...
   ```

3. **Default Implementations**:
   - `DefaultPlanner`: Current behavior (user-provided task_sys_msg)
   - `LLMImplementer`: Current PromptSampler + LLMClient
   - `IslandEvolutionOptimizer`: Current island model + parent selection
   - `MetaAnalyzer`: Current MetaSummarizer

4. **Plugin Architecture**:
   ```python
   # Allow users to provide custom modules
   runner = EvolutionRunner(
       planner=CustomPlanner(),  # User-defined
       implementer=LLMImplementer(),  # Built-in
       optimizer=BayesianOptimizer(),  # Alternative implementation
       analyzer=MetaAnalyzer(),  # Built-in
   )
   ```

**Migration Path**:
- Phase 2.1: Create interfaces, implement default versions
- Phase 2.2: Refactor EvolutionRunner to use interfaces (backward compatible)
- Phase 2.3: Extract custom optimizer implementations
- Phase 2.4: Documentation and examples

---

### Phase 3: Human-in-the-Loop Autonomy Levels (Medium Priority)

**Goal**: Support co-pilot, semi-pilot, autopilot modes

**Implementation**:
1. **Extend `EvolutionConfig`**:
   ```python
   @dataclass
   class EvolutionConfig:
       autonomy_level: str = "autopilot"  # "co-pilot" | "semi-pilot" | "autopilot"
       approval_gates: List[str] = field(default_factory=list)
       # e.g., ["meta_recommendations", "objective_evolution"]
   ```

2. **Approval Gates**:
   ```python
   class ApprovalGate:
       def request_approval(self, action: str, details: Dict) -> bool:
           """Pause evolution and request human approval."""
           # Integration with WebUI
           # Show proposed change, wait for user response
   ```

3. **WebUI Integration**:
   - Add "Review & Approve" panel in WebUI
   - Display proposed objective changes with rationale
   - Show population state and analysis
   - Allow approve/reject/modify

**Use Cases**:
- **Co-pilot**: Review every meta-recommendation before applying
- **Semi-pilot**: Review objective evolution proposals
- **Autopilot**: Current fully autonomous behavior (default)

---

### Phase 4: Multi-Objective Pareto Tracking (Future)

**Goal**: Track Pareto frontier instead of single best score

**Implementation** (conceptual):
```python
class ParetoArchive:
    def add_program(self, program: Program):
        """Add program if it's Pareto-optimal."""
        if self.is_pareto_optimal(program, self.frontier):
            self.frontier.append(program)
            self.remove_dominated(program)

    def sample_diverse_parents(self, k: int) -> List[Program]:
        """Sample parents from across Pareto frontier."""
```

**Visualization**:
- WebUI shows Pareto frontier as scatter plot
- Users can explore trade-offs interactively
- Click program on frontier to see code

---

## Objective Evolution Design Details

### How It Works

**1. Multi-Metric Evaluation**

User's `evaluate.py` returns multiple raw metrics instead of single `combined_score`:

```python
# Traditional (current)
def aggregate_metrics(results):
    return {"combined_score": 0.95}

# Multi-objective (SAGA-inspired)
def aggregate_metrics(results):
    return {
        "correctness": 1.0,
        "speed_score": 0.8,  # 1.0 / execution_time
        "memory_score": 0.9,
        "code_simplicity": 0.7,
        # No combined_score - will be computed dynamically
    }
```

**2. Dynamic Weighting**

ObjectiveEvolver computes `combined_score` from current weights:

```python
# Generation 0-50
weights = {"correctness": 0.3, "speed_score": 0.5, "memory_score": 0.2}
combined_score = 0.3*1.0 + 0.5*0.8 + 0.2*0.9 = 0.88

# Generation 51+ (after detecting reward hacking)
weights = {"correctness": 0.6, "speed_score": 0.25, "memory_score": 0.15}
combined_score = 0.6*1.0 + 0.25*0.8 + 0.15*0.9 = 0.935
```

**3. Reward Hacking Detection**

LLM analyzes population metrics to detect exploits:

**Prompt** (sent to meta-LLM):
```
# Population Metrics (Top 10 Programs)
Program 1: correctness=0.1, speed=0.99, memory=0.95, combined=0.87
Program 2: correctness=0.2, speed=0.98, memory=0.94, combined=0.86
...

# Current Objectives
Weights: {correctness: 0.3, speed: 0.5, memory: 0.2}

# Task
Analyze if high combined_scores come from true optimization or reward hacking.
Look for patterns:
1. One metric consistently maxed while others are low
2. Trade-offs that seem unrealistic
3. Missing important constraints

Recommend new weights if reward hacking detected.
```

**LLM Response**:
```json
{
  "reward_hacking_detected": true,
  "analysis": "Top programs achieve high speed_score by sacrificing correctness.
              Programs return incorrect results quickly. This is reward hacking.",
  "recommended_weights": {
    "correctness": 0.6,
    "speed_score": 0.25,
    "memory_score": 0.15
  },
  "rationale": "Increase correctness weight to prioritize valid solutions."
}
```

**4. Objective Update & Re-scoring**

When objectives evolve:
```python
# Option A: Re-score existing population (cheap, but uses old objectives)
for program in population:
    program.combined_score = compute_score(program.raw_metrics, new_weights)

# Option B: Re-evaluate all programs (expensive, but accurate)
for program in population:
    re_run_evaluation(program)

# Option C: Hybrid - mark programs with objective version
program.objective_version = 2  # Scored with v2 weights
# Only compare programs from same objective version
```

---

### Configuration Example

```yaml
# configs/evolution/saga_objective_evolution.yaml
defaults:
  - /task@_here_: circle_packing

evolution:
  num_generations: 200

  # Objective Evolution
  objective_evolution_enabled: true
  objective_evolution_interval: 50
  objective_base_metrics:
    - sum_radii
    - variance_penalty
    - min_radius_score
    - symmetry_score
  objective_initial_weights:
    sum_radii: 0.7
    variance_penalty: 0.1
    min_radius_score: 0.1
    symmetry_score: 0.1
  objective_evolution_llm_models:
    - azure-gpt-4.1  # Use stronger model for meta-analysis

  # Meta-summarizer (still useful for solution-level insights)
  meta_rec_interval: 25

database:
  # Track which objective version scored each program
  track_objective_versions: true
```

---

### Prompts for Objective Evolution

Located in `genesis/prompts/prompts_objective_evolution.py` (new file):

```python
OBJECTIVE_ANALYSIS_SYSTEM_MSG = """You are an expert at detecting reward hacking in evolutionary optimization systems.

Your task is to analyze whether high-scoring programs achieve their scores through genuine optimization or by exploiting loopholes in the fitness function.

Key concepts:
- **Reward Hacking**: Solutions that maximize the metric without solving the actual problem
- **Goodhart's Law**: "When a measure becomes a target, it ceases to be a good measure"
- **Multi-objective Trade-offs**: Real solutions balance competing objectives; hacks optimize one dimension only

Be skeptical but fair. Not all one-sided metrics indicate hacking - sometimes there's a dominant strategy."""

OBJECTIVE_ANALYSIS_USER_MSG = """# Current Objective Function

Metrics: {base_metrics}
Current Weights: {current_weights}

# Population Statistics (Top {n} Programs)

{population_stats}

# Meta-Analysis Insights

{meta_insights}

# Best Program Examples

{best_program_details}

---

# Analysis Task

1. **Identify Patterns**: Do high-scoring programs share suspicious patterns?
   - One metric maxed while others minimal?
   - Unrealistic trade-offs?
   - Missing crucial constraints?

2. **Reward Hacking Assessment**:
   - Is this genuine optimization or exploitation?
   - What loopholes might exist in the current objective?

3. **Recommendation**:
   - If no hacking: Return current weights unchanged
   - If hacking detected: Propose new weights to address it
   - Explain your reasoning

Return your response as JSON:
{{
  "reward_hacking_detected": true/false,
  "confidence": 0.0-1.0,
  "analysis": "detailed explanation",
  "problematic_patterns": ["pattern1", "pattern2"],
  "recommended_weights": {{"metric1": weight1, ...}},
  "rationale": "why these weights address the issue"
}}"""
```

---

## Benefits of SAGA Integration

### For Users

1. **Less Manual Tuning**: Objectives evolve automatically, reducing need for trial-and-error fitness design
2. **Prevents Reward Hacking**: System detects and corrects exploits
3. **Multi-Objective Awareness**: Better handling of competing goals
4. **Interpretable Evolution**: Clear rationale for why objectives change

### For Researchers

1. **Modular Architecture**: Easier to extend and experiment with components
2. **Research Reproducibility**: Clear separation between solution search and objective refinement
3. **Meta-Learning Opportunities**: Learn which objectives work for which tasks
4. **Benchmark Comparisons**: Compare SAGA-style vs fixed objectives

### For Complex Tasks

Tasks that especially benefit from objective evolution:
- **Multi-objective Optimization**: Circuit design (speed vs power), algorithm design (speed vs memory)
- **Scientific Discovery**: Drug design (efficacy vs toxicity), materials (strength vs cost)
- **Creative Tasks**: Code generation (correctness vs readability vs performance)

---

## Example: Circle Packing with Objective Evolution

### Current Approach (Fixed Objective)

```python
# examples/circle_packing/evaluate.py
def aggregate_circle_packing_metrics(results, results_dir):
    centers, radii, reported_sum = results[0]
    return {
        "combined_score": float(reported_sum),  # Maximize sum of radii
        "public": {
            "num_circles": 26,
            "sum_radii": float(reported_sum),
        }
    }
```

**Problem**: Evolution might find:
- Overlapping circles (violates constraints but increases sum)
- Circles outside boundary (invalid but counted)
- Highly asymmetric packings (mathematically valid but aesthetically poor)

### SAGA-Inspired Approach (Evolving Objective)

```python
# examples/circle_packing_objective_evolution/evaluate.py
def aggregate_circle_packing_metrics(results, results_dir):
    centers, radii, reported_sum = results[0]

    # Compute multiple raw metrics
    variance = np.var(radii)
    min_radius = np.min(radii)
    symmetry = compute_symmetry_score(centers)

    return {
        # Multiple objectives - no single combined_score
        "sum_radii": float(reported_sum),
        "variance_penalty": float(1.0 / (1.0 + variance)),  # Lower variance is better
        "min_radius_score": float(min_radius),  # Avoid tiny circles
        "symmetry_score": float(symmetry),  # Aesthetic consideration
        "public": {
            "num_circles": 26,
            "detailed_stats": {...}
        }
    }
```

**Evolution Timeline**:
- **Gen 0-50**: Focus on `sum_radii` (explore solution space aggressively)
  - Weights: `{sum_radii: 0.8, variance: 0.1, min_radius: 0.05, symmetry: 0.05}`
- **Gen 50**: ObjectiveEvolver detects reward hacking
  - Analysis: "High sum_radii but extreme variance - some circles are tiny"
  - Update: `{sum_radii: 0.5, variance: 0.3, min_radius: 0.15, symmetry: 0.05}`
- **Gen 51-100**: Population shifts toward uniform circles
- **Gen 100**: Another evolution
  - Analysis: "Good uniformity, but asymmetric layout"
  - Update: `{sum_radii: 0.4, variance: 0.3, min_radius: 0.15, symmetry: 0.15}`
- **Gen 101-150**: Discover symmetric high-efficiency packings
- **Gen 150**: Final refinement
  - Analysis: "Pareto frontier reached, balance objectives"
  - Update: `{sum_radii: 0.5, variance: 0.2, min_radius: 0.2, symmetry: 0.1}`

**Result**: Discovers packings that are:
- Efficient (high sum)
- Uniform (low variance)
- Robust (no tiny circles)
- Aesthetic (symmetric)

---

## Related Research

### Papers that Influenced SAGA

1. **Goodhart's Law**: "When a measure becomes a target, it ceases to be a good measure"
2. **Specification Gaming in AI**: [DeepMind, 2020] - catalog of reward hacking examples
3. **Multi-Objective Optimization**: Pareto frontier methods
4. **Automatic Curriculum Learning**: Objectives evolve as agent capabilities grow

### Genesis Papers Using Similar Concepts

From `docs/papers.md`:

- **Eureka** (ICLR 2024): Evolves reward functions for RL via LLM coding
  - Similar to SAGA: objectives (rewards) are code that evolves
  - Difference: RL focus vs general scientific discovery

- **Quality-Diversity through AI Feedback (QDAIF)**: AI evaluates quality + diversity
  - Similar: Multi-objective optimization with AI feedback
  - Difference: Static objectives, no evolution

- **OPRO** (ICLR 2024): LLMs as optimizers
  - Similar: LLM-driven optimization
  - Difference: Optimizes discrete strings, not objectives

---

## Implementation Checklist

### Phase 1: Objective Evolution (Weeks 1-4)
- [ ] Create `genesis/core/objective_evolution.py`
- [ ] Extend `EvolutionConfig` with objective evolution parameters
- [ ] Modify `wrap_eval.py` to support multi-metric returns
- [ ] Add prompts in `genesis/prompts/prompts_objective_evolution.py`
- [ ] Integrate with `MetaSummarizer` for population analysis
- [ ] Update `ProgramDatabase` to store raw metrics and objective versions
- [ ] Add tests for objective evolution logic
- [ ] Create example: `examples/saga_objective_evolution/`
- [ ] Documentation and tutorial

### Phase 2: Modular Architecture (Weeks 5-8)
- [ ] Define interfaces in `genesis/core/interfaces.py`
- [ ] Implement default versions of each module
- [ ] Refactor `EvolutionRunner` to use interfaces
- [ ] Create alternative implementations (Bayesian, MCTS)
- [ ] Migration guide for existing configs
- [ ] Tests for module swapping
- [ ] Documentation: `docs/modular_architecture.md`

### Phase 3: Human-in-the-Loop (Weeks 9-10)
- [ ] Add `autonomy_level` and `approval_gates` to config
- [ ] Implement `ApprovalGate` class
- [ ] WebUI integration for approval requests
- [ ] CLI option for approval in terminal
- [ ] Examples for each autonomy level
- [ ] Documentation and user guide

### Phase 4: Multi-Objective Pareto (Future)
- [ ] Implement `ParetoArchive`
- [ ] Modify parent selection to sample from Pareto frontier
- [ ] WebUI visualization of Pareto frontier
- [ ] Example showcasing Pareto optimization
- [ ] Research paper comparison with NSGA-II, MOEA/D

---

## Conclusion

SAGA's bi-level optimization provides a natural extension to Genesis's current capabilities. While Genesis excels at evolving code (the inner loop), SAGA's outer loop (objective evolution) addresses a fundamental limitation: fixed fitness functions.

**Key Takeaways**:

1. **Complementary Strengths**: Genesis's robust solution search + SAGA's objective evolution
2. **Incremental Adoption**: Can be implemented as opt-in feature without breaking existing workflows
3. **Research Opportunity**: First open-source implementation of SAGA-style objective evolution for code
4. **Practical Impact**: Addresses real pain point of reward hacking in evolutionary systems

**Next Steps**:
1. See `examples/saga_objective_evolution/` for a working prototype
2. Review `docs/modular_architecture.md` for refactoring design
3. Check `ROADMAP.md` for implementation timeline
4. Explore configuration examples in `configs/saga/`

---

## References

- SAGA Paper: https://arxiv.org/html/2512.21782v1
- Genesis Documentation: https://github.com/GeorgePearse/Genesis
- Related Work: `docs/papers.md`
