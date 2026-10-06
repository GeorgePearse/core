# OpenR Integration Ideas for Genesis

## What is OpenR?

OpenR is an open-source framework for advanced reasoning with LLMs, developed to improve mathematical problem-solving and step-by-step reasoning. While Genesis focuses on **code evolution**, OpenR focuses on **reasoning verification and search**.

---

## OpenR's Core Components

### 1. Process Reward Models (PRMs)
**What they do**: Evaluate the quality of *intermediate steps* in a reasoning process, not just the final answer.

**In OpenR**: Used to score each step in mathematical reasoning
- Example: "Is this algebraic manipulation correct?"
- Trained on step-by-step labeled data (or generated via OmegaPRM)

**Potential for Genesis**:
- Score intermediate code states during evolution
- Predict if a mutation is moving in the right direction *before* execution
- Example: "Does this refactoring preserve correctness?" or "Is this optimization likely to help?"

---

### 2. Search Strategies

#### MCTS (Monte Carlo Tree Search)
**What it does**: Builds a search tree where each node represents a state, exploring promising branches more deeply.

**In OpenR**: Each node is a partial solution to a math problem
- Selection: Pick most promising branch (UCB algorithm)
- Expansion: Generate next reasoning step
- Simulation: Complete the solution
- Backpropagation: Update node values

**Potential for Genesis**:
```
Root: Original code (fitness = 0.5)
├─ Mutation 1: Optimize loop (PRM score = 0.7) ← Explore this!
│  ├─ Mutation 1.1: Vectorize (PRM = 0.8)
│  └─ Mutation 1.2: Cache result (PRM = 0.6)
└─ Mutation 2: Change data structure (PRM = 0.3) ← Skip
```

Benefits:
- Avoid wasting evaluations on low-quality mutations
- Systematically explore mutation space
- Can use PRM to guide search without running code

#### Beam Search
**What it does**: At each step, keep only the top-k candidates.

**Potential for Genesis**:
- Instead of islands, maintain a beam of best solutions
- At each generation, generate M mutations per candidate
- Keep only top-k for next generation
- More focused exploration than random sampling

#### Best-of-N + Reranking
**What it does**: Generate N solutions, rank them with a reward model, pick the best.

**Potential for Genesis**:
- Generate N mutations from LLM
- Score each with PRM (fast, no execution)
- Only evaluate top-scoring mutations
- Reduces wasted fitness evaluations

---

### 3. OmegaPRM: Automated Process Supervision

**What it does**: Automatically generates step-by-step supervision data without human labels.

**In OpenR**: 
1. Generate multiple solution paths to the same problem
2. Compare which intermediate steps lead to correct answers
3. Label steps as "good" or "bad" based on outcome

**Potential for Genesis**:
```python
# Evolution trajectory example:
Code v1 (fitness=0.5) 
  → Mutation A → Code v2 (fitness=0.7) ✓ Good mutation!
  → Mutation B → Code v3 (fitness=0.4) ✗ Bad mutation

# Can train PRM on this data:
# "Mutation A-style changes tend to improve fitness"
# "Mutation B-style changes tend to hurt fitness"
```

This creates a **self-supervised learning loop**:
1. Run evolution experiments
2. Collect (mutation, fitness_delta) pairs
3. Train PRM on successful/failed mutations
4. Use PRM to guide future evolution

---

### 4. Online RL Training

**Algorithms**: APPO, GRPO, TPPO

**What they do**: Train the policy (LLM) to maximize rewards through reinforcement learning.

**In OpenR**: Fine-tune LLM to generate better reasoning steps

**Potential for Genesis**:
- Fine-tune the mutation LLM to propose better code changes
- Reward = fitness improvement
- Challenge: Requires many samples (expensive for code evolution)
- Alternative: Use smaller "mutation model" that's cheaper to fine-tune

---

## High-Value Integrations for Genesis

### Priority 1: Process Reward Models (Easy Win)
**Implementation**:
1. Log all evolution runs: `(code_before, mutation, code_after, fitness_delta)`
2. Train simple classifier: `P(mutation_successful | code_before, mutation_description)`
3. Use PRM to filter LLM mutations before evaluation

**Benefits**:
- Reduce wasted evaluations on bad mutations
- Can use static analysis features (AST diff, complexity change, etc.)
- Start simple: Binary classifier (good/bad mutation)

**Example Dataset**:
```json
{
  "code_before": "def fib(n): return fib(n-1) + fib(n-2)",
  "mutation": "Add memoization decorator",
  "code_after": "@lru_cache\ndef fib(n): return fib(n-1) + fib(n-2)",
  "fitness_delta": +0.8,
  "label": "good"
}
```

---

### Priority 2: MCTS for Mutation Search (Medium Effort)

**Implementation**:
```python
class CodeMCTS:
    def search(self, initial_code, budget=100):
        root = Node(code=initial_code, fitness=eval(initial_code))
        
        for _ in range(budget):
            # 1. Selection: Pick promising node
            node = self.select(root)  # UCB algorithm
            
            # 2. Expansion: Generate mutation
            mutation = llm.generate_mutation(node.code)
            child = Node(code=mutation, parent=node)
            
            # 3. Evaluation: Score with PRM (fast) or run code (slow)
            if prm_score(child.code) > threshold:
                child.fitness = evaluate_fitness(child.code)  # Actual run
            else:
                child.fitness = prm_score(child.code)  # Estimated
            
            # 4. Backpropagation: Update ancestors
            self.backprop(child, child.fitness)
        
        return best_node(root)
```

**Benefits**:
- Intelligently allocates evaluation budget
- Can use PRM for cheap "pre-screening"
- Balances exploration vs exploitation

---

### Priority 3: Best-of-N with Learned Filters (Easy Win)

**Current Genesis Flow**:
```
LLM → Mutation → Evaluate → Keep/Discard
```

**With Best-of-N**:
```
LLM → [M1, M2, ..., MN] → PRM scores → Top-K → Evaluate → Keep/Discard
                       ↓
              [0.8, 0.3, 0.9, 0.2, ...]
```

**Implementation**:
```python
# Generate N mutations
mutations = [llm.mutate(code) for _ in range(N)]

# Score with PRM (no execution)
scores = [prm.score(code, mut) for mut in mutations]

# Evaluate only top-K
top_k = sorted(zip(mutations, scores), key=lambda x: x[1], reverse=True)[:K]
results = [evaluate_fitness(mut) for mut, score in top_k]
```

**Benefits**:
- Simple to implement
- Reduces evaluations by factor of N/K
- Can use cheap models (GPT-4o-mini) for PRM

---

## Lower Priority / Research Ideas

### Test-Time Compute Scaling
- Dynamically allocate more mutations to high-fitness candidates
- Spend more LLM calls on "stuck" islands

### Self-Improvement Loop
- Periodically retrain PRM on recent evolution data
- LLM learns from its own successful mutations
- Challenge: Distribution shift as code improves

### Multi-LLM Mutual Reasoning
- Generate mutations from multiple LLMs
- Cross-verify with other LLMs ("Would this mutation help?")
- Ensemble scoring before evaluation

---

## Key Differences: OpenR vs Genesis

| Aspect | OpenR | Genesis |
|--------|-------|---------|
| **Domain** | Mathematical reasoning | Code evolution |
| **Search Space** | Reasoning steps (text) | Code mutations (programs) |
| **Evaluation** | Check final answer | Run code, measure fitness |
| **Evaluation Cost** | Fast (symbolic check) | Slow (execution, sometimes GPU) |
| **Key Insight** | Process > Outcome | Evolution > Single-shot |
| **Bottleneck** | LLM generation quality | Fitness evaluation cost |

**The Big Opportunity**: Genesis spends most time on fitness evaluation. OpenR's PRMs could **predict fitness without execution**, drastically reducing the bottleneck.

---

## Recommended First Steps

1. **Data Collection** (Week 1-2)
   - Modify Genesis to log all mutations with fitness deltas
   - Collect 1000-10000 (mutation, outcome) pairs
   - Include static features: AST diff, code complexity, etc.

2. **Simple PRM** (Week 2-3)
   - Train binary classifier: good/bad mutation
   - Features: Code diff + LLM embeddings
   - Baseline: Random forest or small neural net

3. **Integration** (Week 3-4)
   - Add PRM filtering to `genesis/core/sampler.py`
   - Generate N=10 mutations, evaluate top K=3
   - Measure: Fitness improvement per evaluation

4. **Iterate** (Week 4+)
   - If PRM helps: Invest in MCTS
   - If PRM struggles: Collect more data, try different features
   - Experiment with different N/K ratios

---

## Resources

- **OpenR GitHub**: https://github.com/openreasoner/openr
- **OpenR Paper**: https://arxiv.org/abs/2410.09671
- **OmegaPRM Paper**: https://arxiv.org/abs/2406.06592
- **Math-Shepherd** (similar PRM): https://arxiv.org/abs/2308.04592

