# Inspirations & Framework Patterns

Reference materials and architectural patterns that informed the AI backtesting system design.

## Core Evaluation Frameworks

### 1. Promptfoo
**Best starting point for pattern matching**

- YAML-based test definitions
- GitHub Actions integration for PR-based testing
- Compares "before vs after" prompt changes automatically
- Supports regression testing with assertions
- `promptfoo/promptfoo-action@v1` posts results directly to PRs
- Can use previous outputs as baseline for comparison

**Key Pattern:** Treat prompt/configuration changes like code changes with automated diff testing

**Relevance:** Direct inspiration for YAML test format, assertion types, and PR comparison workflow

---

### 2. DSPy (Stanford NLP)
**Systematic prompt optimization**

- Treats prompts as compiled programs rather than strings
- MIPROv2 optimizer automatically tunes prompts based on metrics
- Uses training/validation sets to measure improvement
- Separates "what the system should do" from "how to prompt it"
- Can automatically generate and test prompt variations

**Key Pattern:** Automatic metric-driven optimization with clear train/test splits

**Relevance:** Inspired assertion registry pattern, optimization loops, and metric-driven evaluation

---

### 3. Evidently + GitHub Actions
**LLM regression testing in CI/CD**

- Released GitHub Action specifically for LLM regression testing
- Downloads test prompts, runs system, evaluates outputs
- Supports LLM judges and custom metrics
- Stores test datasets in cloud for collaboration
- Fails CI if quality metrics drop

**Key Pattern:** Treat AI system changes like code deployments with automated quality gates

**Relevance:** CI/CD integration pattern, GitHub Actions workflow template

---

### 4. CML (Continuous Machine Learning)
**ML-specific CI/CD**

- Integrates with GitHub Actions for ML workflows
- Generates performance reports as PR comments
- Includes visualizations (confusion matrices, metrics graphs)
- Treats model/prompt changes like code deployments

**Key Pattern:** Visual reporting and statistical significance in PR context

**Relevance:** Report generation approach, PR comment formatting

---

## Evaluation Metrics & Methodologies

### Code Quality Metrics (from ML evaluation literature)

**Pass@k (from HumanEval)**
- Probability that at least one of k samples passes tests
- Gold standard for code generation evaluation
- Simple, well-understood, reproducible
- **Recommendation:** Start with this metric

**CodeBLEU**
- BLEU adapted for code with Abstract Syntax Tree awareness
- Better for semantic similarity than character-level metrics
- Accounts for structure, not just surface similarity

**ChrF (Character n-gram F-score)**
- Shown to correlate better with human judgment than BLEU
- Less sensitive to minor variations
- Better for evaluation flexibility

**Code Quality Analysis**
- Cyclomatic complexity metrics
- Lint errors (pylint, ruff scores)
- Static analysis violations
- Execution performance metrics
- Test coverage metrics

**Comparison Metrics**
- Relative improvement/degradation percentages
- Statistical significance testing (critical!)
- Small improvements (<2 points) often aren't statistically significant

---

## Historical PR Mining Patterns

### RepoBench Approach
- Mines real code completion scenarios from GitHub history
- Uses real development context
- Pattern: Historical ground truth as validation

**Application:** Extract PR descriptions → expected code changes as test cases

### SWE-bench Pattern
- Uses real GitHub issues and their fixes as test cases
- Evaluates if AI reproduces actual developer solutions
- Realistic, complex scenarios
- Pattern: Real-world problem sets

**Application:** Historical successful PRs as "golden" test cases; measure if config changes maintain solution quality

### Your Innovation: PR History as Test Strategy
**Key insight:** Using historical PRs as backtesting data is like using historical trades in finance
- Extract problem (PR description/context) → solution (PR diff)
- Test new configurations against proven solutions
- Measure: "Does new config still produce acceptable fixes for this real scenario?"

---

## MCP-Specific Testing Patterns

### MCP Security Testing (from Promptfoo)
- Tests MCP servers with malicious/edge-case inputs
- Evaluates agent behavior with potentially problematic tool outputs
- Chain-of-thought validation

**Pattern:** Test full execution chain, not just the prompt

### Agent Framework Testing
- Build test harnesses that simulate full agent interactions
- Test tool selection accuracy
- Measure cascading effects of configuration changes
- Context window optimization tests

**Pattern:** Test in realistic execution context, not isolation

---

## Data Collection & Context Tools

### OneFileLLM
**Content aggregator for building realistic evaluation datasets**

- Pulls information from diverse sources into structured XML format
- **Supported sources:** Local files/directories, GitHub repos/PRs/issues, documentation sites, ArXiv papers, DOIs, PubMed, YouTube transcripts, stdin/clipboard
- Customizable aliases with dynamic placeholders
- Advanced web crawling control (exclude images, code, CSS as needed)
- Direct piping to other LLM tools for multi-stage analysis

**Key Pattern:** Automated test case collection from diverse real-world sources

**Relevance:** Could automate gathering historical PRs, related documentation, and context for creating realistic evaluation datasets. Useful for:
- Mining PR descriptions and actual solutions from GitHub
- Collecting related documentation for context window testing
- Aggregating knowledge base for comprehensive evaluation scenarios

---

## Diff Representation and Scoring

### The Core Challenge

When using historical PRs as test cases, you need to evaluate whether generated code matches (or improves upon) the actual PR changes. The challenge: **exact string matching is too strict** because:

- Different variable names / formatting / code style can be functionally equivalent
- Multiple solutions may solve the same problem equally well
- Comments and docstrings may differ but intent is the same
- Small refactorings might be superior to the original

**Core Question:** How do you score "closeness" between expected diff (actual PR) and generated diff (AI output)?

---

### Diff Representation Approaches

#### 1. Semantic Patch Format (Like Coccinelle)
```json
{
  "changes": [
    {
      "file": "src/main.py",
      "hunks": [
        {
          "type": "replace",
          "before": "def process(data):\n    return data * 2",
          "after": "def process(data, scale=2):\n    return data * scale",
          "context": {"function": "process", "line": 42}
        }
      ]
    }
  ]
}
```

**Strengths:** Human-readable, captures intent, hunk-level granularity
**Use for:** PR-level diff comparison with context

#### 2. AST-Based Diff (Most Robust for Code)
```json
{
  "file": "main.py",
  "ast_changes": [
    {
      "operation": "add_parameter",
      "path": "FunctionDef.process.args",
      "value": {"name": "scale", "default": 2}
    },
    {
      "operation": "modify_expression",
      "path": "FunctionDef.process.body[0].value",
      "from": "BinOp(left=Name('data'), op=Mult, right=Constant(2))",
      "to": "BinOp(left=Name('data'), op=Mult, right=Name('scale'))"
    }
  ]
}
```

**Strengths:** Semantic understanding, immune to formatting, captures structure
**Use for:** Detailed refactoring analysis, comparing non-obvious changes

#### 3. Hybrid Line + Semantic Representation
```python
class DiffHunk:
    # Line-level for easy comparison
    removed_lines: List[str]
    added_lines: List[str]

    # Semantic understanding
    change_type: Literal["refactor", "bugfix", "feature", "optimization"]
    entities_modified: List[str]  # ["function:process", "parameter:scale"]

    # For scoring partial matches
    key_operations: List[str]  # ["add_parameter", "replace_constant_with_variable"]
```

**Strengths:** Combines line-level matching with semantic understanding
**Use for:** Practical balanced approach, enables partial credit scoring

---

### Multi-Level Scoring System

**Recommended approach: Tiered evaluation with fallback strategy**

```python
def score_diff_similarity(actual_diff, generated_diff):
    scores = {
        # Exact match - did they get it perfect?
        'exact_match': (actual == generated),  # 0 or 1

        # Line-level - how many lines match?
        'line_precision': matching_lines / generated_lines,
        'line_recall': matching_lines / actual_lines,

        # Semantic - did they understand the change?
        'semantic_similarity': calculate_ast_similarity(actual, generated),

        # Partial credit - useful changes even if not exact
        'useful_changes': count_beneficial_changes(generated) / total_changes,

        # Syntax validity - does it even work?
        'compiles': does_code_compile(apply_diff(base, generated)),
        'tests_pass': do_tests_pass(apply_diff(base, generated))
    }

    # Weighted combination
    return weighted_average(scores, weights={
        'exact_match': 0.3,
        'semantic_similarity': 0.3,
        'tests_pass': 0.2,
        'line_precision': 0.1,
        'line_recall': 0.1
    })
```

**Scoring Metrics:**
- **Exact Match (30%):** Binary - perfect reproduction of the diff
- **Semantic Similarity (30%):** AST-based comparison, immune to style/naming
- **Tests Pass (20%):** Functional correctness - generated code must pass tests
- **Line Precision (10%):** Efficiency of changes - minimal unnecessary additions
- **Line Recall (10%):** Completeness - didn't miss important changes

---

### Existing Tools to Leverage

#### GumTree
- AST-based diff comparison for code
- Detects tree operations and similarities
- Pattern: `diff_trees(before_ast, actual_ast, generated_ast)` returns `similarity_score()`

#### diff-match-patch (Google)
- Fuzzy text matching for diffs
- Handles minor variations and similar structures
- Good for fallback when exact match fails

#### RefactoringMiner
- Automatically detects change types: extract method, rename, move, etc.
- Classifies refactoring operations semantically
- Useful for understanding intent behind generated changes

---

### Recommended Three-Tier Approach

**Key Insight:** Try levels in order of strictness, fall back when needed

```python
class PRDiff:
    # Tier 1: Raw representation (for exact matching)
    unified_diff: str  # Standard git diff format

    # Tier 2: Structured representation (for partial credit)
    hunks: List[DiffHunk]  # Parsed changes with context

    # Tier 3: Semantic representation (for understanding intent)
    change_summary: {
        'intent': str,  # "Add error handling to API endpoint"
        'operations': List[str],  # ["add_try_catch", "add_logging"]
        'affected_symbols': List[str],  # ["UserAPI.get_user", "logger"]
    }

def evaluate_pr_generation(actual_pr: PRDiff, generated: str) -> Score:
    """Evaluate generated code against actual PR with fallback strategy"""
    gen_diff = parse_to_diff(generated)

    # Try levels in order of strictness
    if gen_diff.unified_diff == actual_pr.unified_diff:
        return Score(1.0, "exact_match", "Perfect reproduction")

    if semantic_equivalent(gen_diff.hunks, actual_pr.hunks):
        return Score(0.8, "semantic_match", "Same intent, different style")

    if achieves_same_goal(gen_diff, actual_pr):
        return Score(0.6, "functional_match", "Works but different approach")

    if shows_understanding(gen_diff, actual_pr):
        return Score(0.3, "partial_match", "Some understanding shown")

    return Score(0.0, "no_match", "Fundamentally different solution")
```

**This mirrors programming homework grading:**
- ✅ Perfect solution (100%)
- ✅ Right approach, minor issues (80%)
- ✅ Shows understanding, different method (60%)
- ⚠️ Partial understanding (30%)
- ❌ Fundamentally wrong (0%)

---

### Applications to Backtesting

**For evaluating MCP/Agent configuration changes:**

1. **Extract test case from PR:**
   - Problem: PR description/context
   - Expected solution: Actual PR diff

2. **Run with new configuration:**
   - Generate code with updated config
   - Extract generated diff

3. **Score similarity:**
   - Exact match: 100%
   - Semantic match: 80%
   - Functional match: 60%
   - Partial match: 30%
   - No match: 0%

4. **Report results:**
   - Track which PRs pass at which thresholds
   - Identify regression patterns
   - Measure average quality across test suite

---

**Why this analogy works perfectly:**

| Finance | Code Generation |
|---------|-----------------|
| Strategy | Configuration (MCP, AGENTS.md, prompts) |
| Historical trades | Historical PRs |
| Performance metrics | Code quality metrics (Pass@k, CodeBLEU) |
| Walk-forward testing | PR replay testing |
| Drawdown | Quality degradation |
| Sharpe ratio | Code quality improvement ratio |
| Curve fitting risk | Overfitting to specific PR types |

**Key benefits of this frame:**
- Borrows rigorous statistical methodology
- Built-in concepts like significance testing, risk quantification
- Natural progression: backtest → forward test → live
- Familiar framework for engineers who trade/invest

---

## Similar/Competitive Tools to Study

### DeepEval
- Pytest-like testing framework for LLMs
- Pattern: Assertion-based evaluation
- Reference for assertion design

### LangSmith (LangChain's platform)
- Tracing and evaluation
- Dataset management
- Run comparison
- Reference for dataset handling

### Weights & Biases (wandb)
- ML/LLM evaluation features
- Visualization and comparison
- Reference for metrics visualization

### MLflow
- Model evaluation and comparison
- Artifact storage
- Experiment tracking
- Reference for artifact management

### Giskard
- Open-source ML testing framework
- Robustness testing patterns
- Reference for edge-case testing

### LightEval (Hugging Face)
- All-in-one toolkit for evaluating LLMs across multiple backends
- 7,000+ evaluation tasks: MMLU, GSM8K, MATH, multilingual (Flores200)
- Flexible deployment: Accelerate, VLLM, SGLang, Nanotron, inference endpoints
- Custom task and metric creation
- Sample-by-sample result debugging for model performance analysis
- Support for specialized evaluations (RULER for long-context, MT-Bench for dialogue)

**Key Pattern:** Comprehensive benchmark library with flexible backend support

**Relevance:** Reference for building extensible task/metric registry, multi-backend support design

---

## Key Architectural Patterns to Borrow

### 1. Pytest Plugin Pattern
- Discover test files by convention
- Dynamic test node creation
- Native CI/CD integration
- Standard output formats

### 2. Configuration as Code
- YAML for test definitions (Promptfoo style)
- Human-readable, version-controllable
- Easy to understand without code

### 3. Lazy Evaluation
- Cache expensive operations (LLM calls)
- Deterministic hashing for reproducibility
- Cost optimization built-in

### 4. Pluggable Validators
- Registry pattern for custom validators
- Composition over inheritance
- Easy to extend without modifying core

### 5. Progressive Reporting
- Simple text reports for CLI
- HTML reports for sharing
- Markdown for GitHub integration
- Structured output (JSON) for automation

---

## Implementation Priority Guidance

**From studying these frameworks:**

### Start Simple
1. Pass@k metric (simple, proven)
2. Deterministic assertions (regex, string matching)
3. Basic regression detection

### Add Gradually
4. LLM-as-judge for qualitative metrics
5. Code quality metrics (CodeBLEU, complexity)
6. Statistical significance testing

### Optimize Last
7. Automatic prompt/config tuning (DSPy-style)
8. Advanced visualization
9. Cost optimization through caching

---

## Citation/Attribution

This system synthesizes patterns from:
- **Promptfoo** (YAML tests, GitHub Actions integration)
- **DSPy** (Optimizer patterns, assertion framework)
- **Evidently** (LLM evaluation in CI/CD)
- **HumanEval/CodeBLEU** (Metrics)
- **Finance/Backtesting literature** (Methodology and statistical rigor)
- **SWE-bench/RepoBench** (Historical PR mining)
- **Pytest** (Test discovery and plugin system)
- **LightEval** (Benchmark library design, extensible task/metric registry)
- **OneFileLLM** (Automated context/test case collection)
- **GumTree/diff-match-patch/RefactoringMiner** (Diff representation and scoring)

The key innovation: Combining all these patterns specifically for MCP/Agent configuration validation through historical PR backtesting with multi-tier diff scoring for fair evaluation of generated code against actual solutions.

---

## Further Reading

### Papers & References
- HumanEval: https://github.com/openai/human-eval
- CodeBLEU: https://arxiv.org/abs/2009.10297
- SWE-bench: https://github.com/princeton-nlp/swe-bench
- RepoBench: https://arxiv.org/abs/2403.03989

### Frameworks
- Promptfoo: https://github.com/promptfoo/promptfoo
- DSPy: https://github.com/stanfordnlp/dspy
- DeepEval: https://github.com/confident-ai/deepeval
- Giskard: https://github.com/Giskard-AI/giskard
- LightEval: https://github.com/huggingface/lighteval
- OneFileLLM: https://github.com/jimmc414/onefilellm

### Diff Tools & Techniques
- GumTree: https://github.com/GumTreeDiff/gumtree
- diff-match-patch: https://github.com/google/diff-match-patch
- RefactoringMiner: https://github.com/danilofes/refactoring-miner
