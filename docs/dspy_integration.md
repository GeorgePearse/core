# DSPy Integration Concepts

[DSPy](https://github.com/stanfordnlp/dspy) revolutionizes LLM usage by separating **logic** (signatures) from **parameters** (prompts/weights) and introducing **optimizers** (teleprompters) to tune those parameters.

Here is how Genesis can leverage DSPy concepts:

## 1. Prompt Optimization (The "Compiler")

Currently, Genesis uses fixed prompt templates (e.g., `DIFF_SYS_FORMAT`). If the prompt is suboptimal, the evolution suffers.

**DSPy Inspiration**: **MIPRO (Multi-prompt Instruction Proposal Optimizer)**

We can implement an **Outer Optimization Loop**:

1.  **Define Metric**: Average population fitness over 5 generations.
2.  **Propose**: A "Prompt LLM" generates 10 variations of the `task_sys_msg` (e.g., one emphasizes "speed", another "readability", another "step-by-step").
3.  **Evaluate**: Run a short Genesis evolution sprint for each prompt variation.
4.  **Select**: Keep the prompt that produced the best code.

**Implementation**:
```python
class PromptOptimizer:
    def optimize(self, base_config):
        candidates = self.generate_prompt_candidates(base_config.task_sys_msg)
        scores = []
        for prompt in candidates:
            # Run "Micro-Genesis"
            avg_fitness = self.run_short_experiment(prompt)
            scores.append(avg_fitness)
        return candidates[np.argmax(scores)]
```

## 2. Bootstrapping Few-Shot Examples

Genesis uses "Inspirations" (Archive/Top-K) as few-shot examples. Currently, this is a heuristic selection (random or fitness-weighted).

**DSPy Inspiration**: **BootstrapFewShot**

DSPy's BootstrapFewShot runs the pipeline, collects successful traces (Input -> Output pairs that scored high), and permanently saves them as few-shot examples for future calls.

**Genesis Adaptation**:
Instead of *just* showing top-k programs, we should explicitly curate a "Golden Set" of **Mutation Traces**:
- `(Code_Before, Mutation_Instruction, Code_After)` pairs that resulted in huge fitness jumps.
- The system should "learn" which examples are most instructive. If showing "SIMD optimization" examples leads to failures, stop showing them. If showing "Memory layout" changes leads to success, pin those examples in the prompt.

## 3. Signatures vs. Strings

DSPy encourages defining tasks as **Signatures**: `class CodeImprover(dspy.Signature): "input_code -> improved_code"`.

**Genesis Adaptation**:
Refactor `genesis/prompts/` to define Signatures. This allows us to easily swap out the underlying prompt structure (Chain of Thought, ReAct, etc.) without rewriting the entire string handling logic.

```python
class EvolveSignature(dspy.Signature):
    """Improve the provided code to maximize the fitness metric."""
    code: str = dspy.InputField()
    performance_feedback: str = dspy.InputField()
    improved_code: str = dspy.OutputField()
```

## Strategy

1.  **Short Term**: Implement the "Outer Loop" prompt optimizer (MIPRO-lite) to tune `task_sys_msg`.
2.  **Medium Term**: Replace heuristic "Inspirations" with a learned "Few-Shot Bootstrap" set of high-impact mutations.
3.  **Long Term**: Adopt DSPy (or a similar abstraction) to manage the prompt construction pipeline entirely.
