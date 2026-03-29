# SAGA Objective Evolution Prototype

This example demonstrates the SAGA paper's concept of **objective evolution** applied to Genesis.

## The Problem: Reward Hacking

When optimizing algorithms, LLMs can exploit loopholes in fitness functions:

**Task**: Optimize a sorting algorithm for speed
**Fixed Fitness**: `combined_score = 1.0 / execution_time`
**Reward Hack**: Return empty list (fastest, but incorrect!)

## SAGA's Solution: Evolve the Objective

Instead of fixing the fitness function, let it evolve:

1. **Generation 0-50**: Optimize `1.0 / execution_time`
2. **Detect**: High scores but incorrect results
3. **Evolve Objective**: Add correctness penalty
4. **Generation 51+**: Optimize `correctness * (1.0 / execution_time)`

## Prototype Overview

This directory contains a **conceptual prototype** demonstrating objective evolution logic. It shows:

- How to detect reward hacking patterns in population metrics
- How to propose objective weight adjustments
- The structure of bi-level optimization (outer loop for objectives, inner loop for solutions)

**Note**: This is a simplified standalone prototype. Production implementation would integrate with Genesis's MetaSummarizer and database infrastructure.

## Files

- `objective_evolver.py`: Prototype bi-level optimization logic
- `README.md`: This file

## Expected Behavior

**Fixed Objective Scenario**:
- Fast convergence to reward-hacked solutions
- High combined_score but low correctness

**Evolving Objective Scenario**:
- Initial focus on speed (explore solution space)
- Detect reward hacking around generation 20
- Reweight to balance speed + correctness
- Converge to truly optimal solutions

## Example Usage

```python
from objective_evolver import SimpleObjectiveEvolver

# Initialize with base metrics and initial weights
evolver = SimpleObjectiveEvolver(
    base_metrics=['correctness', 'speed_score', 'memory_score'],
    initial_weights={'correctness': 0.2, 'speed_score': 0.6, 'memory_score': 0.2}
)

# Simulate population with reward hacking
population_metrics = [
    {'correctness': 0.1, 'speed_score': 0.95, 'memory_score': 0.8},
    {'correctness': 0.2, 'speed_score': 0.90, 'memory_score': 0.7},
    # ... more programs
]

# Analyze and evolve objectives
new_weights, reason = evolver.analyze_and_evolve(population_metrics, generation=50)

print(f"Evolution reason: {reason}")
print(f"New weights: {new_weights}")
# Output: "Reward hacking detected: speed=0.925 but correctness=0.15.
#          Increasing correctness weight."
# New weights: {'correctness': 0.5, 'speed_score': 0.3, 'memory_score': 0.2}
```

## Integration with Genesis

Full integration would add to `genesis/core/`:
- `objective_evolution.py` module (production version)
- Extensions to `EvolutionConfig` for objective evolution parameters
- Integration with `MetaSummarizer` for LLM-driven analysis
- Database tracking of objective versions
- Support for multi-metric evaluation without `combined_score`

See `docs/saga_integration.md` for complete design.

## Related Research

- SAGA Paper: https://arxiv.org/html/2512.21782v1
- Genesis SAGA Integration: `docs/saga_integration.md`
- Modular Architecture Design: `docs/modular_architecture.md`

## Future Extensions

- LLM-driven objective analysis (currently uses simple heuristics)
- Pareto frontier tracking for multi-objective optimization
- Three-tier autonomy (co-pilot/semi-pilot/autopilot) for human approval
- WebUI visualization of objective evolution timeline
- Integration with Genesis database for population-wide analysis
