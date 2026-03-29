# Creating Custom Tasks 🛠️

Genesis is designed to be easily extensible to new tasks. A "task" in Genesis is defined by a problem to solve (e.g., optimize a function, generate a specific output) and a way to evaluate solutions.

This guide walks you through the process of creating a new custom task from scratch.

## Task Structure

A typical task in Genesis consists of three main components:

1.  **Initial Solution (`initial.py`)**: The starting point code that contains the logic to be evolved.
2.  **Evaluation Script (`evaluate.py`)**: A script that runs the evolved code and scores it.
3.  **Configuration**: YAML files that tell Genesis how to run your task.

We recommend organizing your task files in the `examples/` directory:

```
examples/
  my_new_task/
    initial.py     # Starting code with EVOLVE-BLOCKs
    evaluate.py    # Logic to score candidate solutions
```

## Step 1: Create the Initial Solution

The initial solution is a valid Python program that performs the task, even if poorly. Genesis uses LLMs to modify specific parts of this code.

Create `examples/my_new_task/initial.py`:

```python
import numpy as np

# EVOLVE-BLOCK-START
def my_algorithm(x):
    """
    This function will be evolved by Genesis.
    Goal: Implement a function that returns x squared.
    """
    # Initial dumb implementation
    return x * 1
# EVOLVE-BLOCK-END

def run_experiment(x_value):
    """
    Wrapper function called by the evaluator.
    """
    return my_algorithm(x_value)
```

**Key Concepts:**
*   **`EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END`**: These markers tell Genesis which lines of code the LLM is allowed to modify. Code outside these blocks remains constant.
*   **Entry Point**: You need a function (like `run_experiment`) that the evaluation script can call to execute the candidate solution.

## Step 2: Create the Evaluation Script

The evaluation script is responsible for:
1.  Importing the candidate solution (which Genesis will generate).
2.  Running it against test cases.
3.  Calculating a "fitness score" (higher is better).
4.  Reporting results back to Genesis.

Create `examples/my_new_task/evaluate.py`:

```python
import sys
import os
from genesis.core import run_genesis_eval

def validate_solution(output):
    """
    Optional: specific validation logic (e.g., check types, constraints).
    Returns (is_valid, error_message).
    """
    if not isinstance(output, (int, float)):
        return False, "Output must be a number"
    return True, None

def aggregate_metrics(results, results_dir):
    """
    Computes the final score from multiple test runs.
    """
    # results is a list of outputs from run_experiment
    # In this simple example, we just have one result or handle list
    
    total_error = 0
    # Let's say we passed x=10, expecting 100
    expected = 100
    actual = results[0]
    
    error = abs(expected - actual)
    
    # We want to MAXIMIZE score, so we can use negative error or 1/(1+error)
    score = 1.0 / (1.0 + error)
    
    return {
        "combined_score": float(score),  # REQUIRED: Primary fitness metric
        "public": {                      # displayed in logs/WebUI
            "error": float(error),
            "actual_value": float(actual)
        },
        "private": {}                    # internal debug data
    }

def get_experiment_kwargs(run_idx):
    """
    Returns arguments to pass to the candidate's run_experiment function.
    Can vary per run for stochastic evaluation.
    """
    return {"x_value": 10}

def main(program_path: str, results_dir: str):
    """
    Main entry point called by Genesis.
    """
    metrics, correct, error_msg = run_genesis_eval(
        program_path=program_path,
        results_dir=results_dir,
        experiment_fn_name="run_experiment",  # Function to call in candidate code
        num_runs=1,                           # How many times to run it
        get_experiment_kwargs=get_experiment_kwargs,
        validate_fn=validate_solution,
        aggregate_metrics_fn=aggregate_metrics,
    )

if __name__ == "__main__":
    # Genesis passes these arguments automatically
    if len(sys.argv) < 3:
        print("Usage: python evaluate.py <program_path> <results_dir>")
        sys.exit(1)
        
    main(sys.argv[1], sys.argv[2])
```

## Step 3: Configure the Task

Now you need to tell Genesis about your task using Hydra configuration. You can create a dedicated task config file.

Create `configs/task/my_new_task.yaml`:

```yaml
# Task-specific evaluation function configuration
evaluate_function:
  _target_: examples.my_new_task.evaluate.main
  program_path: ???  # Placeholder, filled at runtime
  results_dir: ???   # Placeholder, filled at runtime

# Job configuration (where/how to run the evaluation)
distributed_job_config:
  _target_: genesis.launch.LocalJobConfig
  eval_program_path: "examples/my_new_task/evaluate.py"

# Evolution configuration overrides for this task
evo_config:
  task_sys_msg: |
    You are an expert Python programmer.
    Your goal is to implement a function that calculates the square of a number.
    Optimize for correctness and clean code.
  
  language: "python"
  init_program_path: "examples/my_new_task/initial.py"
  job_type: "local"

exp_name: "my_new_task_experiment"
```

## Step 4: Run the Evolution

You can now run your task using `genesis_launch` by combining your task config with other default configs.

The easiest way is to use the `task` argument:

```bash
genesis_launch \
    task=my_new_task \
    database=island_small \
    evolution=small_budget \
    cluster=local
```

### Creating a Reusable Variant (Optional)

If you run this configuration often, create a "variant" file in `configs/variant/my_task_variant.yaml`:

```yaml
defaults:
  - override /database@_global_: island_small
  - override /evolution@_global_: small_budget
  - override /task@_global_: my_new_task
  - override /cluster@_global_: local
  - _self_

# You can add further overrides here
evo_config:
  num_generations: 50

variant_suffix: "_my_task_run"
```

Then run it simply with:

```bash
genesis_launch variant=my_task_variant
```

## Advanced: Optimizing Other Languages (Rust, C++, etc.)

Genesis can optimize code in any language!

1.  **Initial Code**: Write `initial.rs` (or `.cpp`, etc.) with `EVOLVE-BLOCK` comments.
2.  **Configuration**: Set `evo_config.language: "rust"` (helps the LLM with syntax).
3.  **Evaluator**: Your `evaluate.py` simply needs to:
    *   Read the candidate file path provided by Genesis.
    *   Compile the code (e.g., `subprocess.run(["rustc", candidate_path])`).
    *   Run the binary and capture output.
    *   Parse the output to compute the fitness score.

See `examples/mask_to_seg_rust/` for a concrete example.
