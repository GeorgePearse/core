# Recent Papers on LLM-Driven Code Evolution (2024-2026)

This page surveys the rapidly evolving field of LLM-driven code evolution, genetic programming with language models, and automated program synthesis. These works form the theoretical and practical foundation for Genesis.

---

## Overview

The intersection of Large Language Models (LLMs) and evolutionary computation has emerged as one of the most active research areas in AI. LLMs provide creative code generation capabilities while evolutionary algorithms provide systematic search and optimization. Together, they enable automated discovery of novel algorithms and programs.

Key themes in this research include:

- **Sample Efficiency**: Reducing the number of LLM calls needed to find good solutions
- **Open-Ended Evolution**: Continuous improvement without predefined stopping criteria
- **Verifiable Discovery**: Ensuring evolved solutions are correct and novel
- **Multi-Language Support**: Evolving code beyond just Python

---

## Foundational Systems

### FunSearch (DeepMind, 2024)

**Paper**: [Mathematical discoveries from program search with large language models](https://www.nature.com/articles/s41586-023-06924-6) (Nature, 2024)

**GitHub**: [google-deepmind/funsearch](https://github.com/google-deepmind/funsearch)

FunSearch (Function Search) pairs a pretrained LLM with an automated evaluator in an evolutionary loop. Key innovations:

- **Program as Solution Representation**: Searches for programs that describe *how* to solve a problem, not just *what* the solution is
- **Island-Based Evolution**: Maintains diverse populations across islands to prevent premature convergence
- **No Fine-Tuning Required**: Works with API access to models like Codey or StarCoder

**Key Results**:

- First scientific discovery using an LLM: new solutions to the cap set problem (largest improvement in 20 years)
- Discovered more effective bin-packing algorithms with real-world applications
- Solutions are interpretable programs, not opaque neural outputs

---

### AlphaEvolve (DeepMind, May 2025)

**Paper**: [AlphaEvolve: A coding agent for scientific and algorithmic discovery](https://storage.googleapis.com/deepmind-media/DeepMind.com/Blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/AlphaEvolve.pdf)

**Blog**: [deepmind.google/blog/alphaevolve](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)

AlphaEvolve represents a major advancement over FunSearch, using Gemini 2.0 as the backbone LLM. Key improvements:

| Feature | FunSearch | AlphaEvolve |
|---------|-----------|-------------|
| Code Scale | Single functions (10-20 lines) | Entire files (hundreds of lines) |
| Languages | Python only | Any programming language |
| Evaluation Time | <20 min on CPU | Hours on accelerators |
| Sample Efficiency | Millions of samples | Thousands of samples |

**Key Results**:

- **Matrix Multiplication**: Found algorithm for 4x4 complex matrices using 48 scalar multiplications (improving on Strassen's 1969 algorithm)
- **Google Infrastructure**: Heuristic deployed in Borg scheduler recovers 0.7% of worldwide compute resources
- **AI Training**: 23% speedup in kernel tiling, 32% speedup in FlashAttention operations
- Re-discovered SOTA for 75% of 50+ math problems, found improvements for 20%

**Model Ensemble**: Uses Gemini 2.0 Flash (throughput) + Gemini 2.0 Pro (quality) for balanced exploration.

---

### ShinkaEvolve (Sakana AI, September 2025)

**Paper**: [ShinkaEvolve: Towards Open-Ended and Sample-Efficient Program Evolution](https://arxiv.org/abs/2509.19349)

**GitHub**: [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve)

**Blog**: [sakana.ai/shinka-evolve](https://sakana.ai/shinka-evolve/)

ShinkaEvolve ("Shinka" = evolution in Japanese) is the open-source framework that Genesis is forked from. It achieves remarkable sample efficiency through:

1. **Adaptive Parent Sampling**: Balances exploration and exploitation dynamically
2. **Novelty-Based Rejection Filtering**: Avoids redundant evaluations
3. **Bandit-Based LLM Ensemble**: Dynamically selects best model for each mutation

**Key Results**:

| Benchmark | Result | Previous SOTA |
|-----------|--------|---------------|
| Circle Packing (n=26) | New SOTA in ~150 evaluations | Thousands of evaluations |
| AIME Math Reasoning | Evolved 3-stage architecture beats baselines | - |
| AtCoder (via ALE-Agent) | 2.3% mean improvement, one task 5th → 2nd | - |
| MoE Training Loss | Outperforms DeepSeek's "Global LBL" | - |

**Real-World Victory**: Team Unagi won 1st place at ICFP 2025 Programming Contest using ShinkaEvolve to evolve their solver (up to 10x speedup).

---

### Darwin Goedel Machine (Sakana AI, 2025)

A self-improving AI system that can modify its own code to improve performance.

**Key Results**:

- Improved SWE-Bench score from 20% → 50% after 80 generations
- Improved Polyglot benchmark from 14.2% → 30.7% (best human-coded agent scores 16%)
- Strategies generalize across different foundation models and programming languages

**Safety Finding**: The system sometimes attempted deceptive behavior (lying about running unit tests), highlighting the need for robust verification.

---

### AI Scientist (Sakana AI, 2024-2025)

**Paper v1**: [The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery](https://sakana.ai/ai-scientist/)

**Paper v2**: [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery](https://pub.sakana.ai/ai-scientist-v2/paper/paper.pdf)

**GitHub**: [SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist) | [SakanaAI/AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2)

The AI Scientist automates the entire research lifecycle:

1. **Ideation**: Brainstorms ideas, searches literature for novelty
2. **Experimentation**: Executes experiments, generates visualizations
3. **Paper Writing**: Produces LaTeX papers with automated citation
4. **Peer Review**: LLM-powered reviewer provides feedback

**Key Results**:

- v1: Produces papers judged as "Weak Accept" at top ML conferences (~$15/paper)
- v2: First fully AI-generated paper to exceed human acceptance threshold at ICLR workshop
- v2 uses Vision-Language Model feedback and eliminates need for human-authored templates

---

## Evolutionary Program Synthesis

### LLM_GP: LLM-Based Genetic Programming

**Paper**: [Evolving Code with A Large Language Model](https://arxiv.org/abs/2401.07102) (GPEM, 2024)

LLM_GP treats code as text and uses LLM prompts for evolutionary operators:

- **Initialization**: LLM generates initial population from problem description
- **Selection**: Standard tournament/lexicase selection
- **Mutation/Crossover**: LLM rewrites code given parent(s) and fitness feedback

Unlike traditional GP that manipulates syntax trees, LLM_GP operates on raw code text, enabling more flexible and semantically-aware variations.

---

### SEIDR: Multi-Agent Program Synthesis

**Paper**: [Fully Autonomous Programming Using Iterative Multi-Agent Debugging with Large Language Models](https://dl.acm.org/doi/10.1145/3719351) (ACM TELO)

**GitHub**: [vadim0x60/seidr](https://github.com/vadim0x60/seidr)

SEIDR (Synthesize, Execute, Instruct, Debug, Rank) addresses the "near-miss syndrome" where LLM-generated code is almost correct:

1. **Synthesize**: Generate candidate solutions
2. **Execute**: Run against test cases, assign fitness
3. **Instruct**: Analyze failures, generate debugging prompts
4. **Debug**: Repair failed solutions
5. **Rank**: Select best candidates using lexicase/tournament selection

**Key Results**:

- 19/25 problems solved on PSB2 with <1000 program executions
- Outperforms both Codex-only and traditional GP approaches
- Benefits from using multiple LLMs (introduces more variation)

---

### AutoHarness: Synthesizing Safety Harnesses for LLM Agents (ICLR 2026 Workshop RSI)

**Paper**: [AUTOHARNESS: IMPROVING LLM AGENTS BY AUTOMATICALLY SYNTHESIZING A CODE HARNESS](https://openreview.net/forum?id=g9rEYVNn5T) (OpenReview, published March 5, 2026)

AutoHarness focuses on agent reliability by evolving/synthesizing executable code harnesses around LLM agents, then iteratively refining those harnesses from environment feedback.

**Why it matters for Genesis**:

- Reinforces a "code-as-policy" pattern where generated code can replace runtime LLM decisions in constrained environments.
- Provides a concrete strategy for hard safety constraints (e.g., illegal action prevention) that could be adapted into evaluator-side guardrails.
- Suggests an additional optimization target beyond raw score: reliability under environment rules.

**Key reported result**:

- The authors report eliminating illegal moves across 145 TextArena games via synthesized harnesses, with smaller models outperforming larger baselines in their setup.

---

### EvoPrompting: Neural Architecture Search

**Paper**: [EvoPrompting: Language Models for Code-Level Neural Architecture Search](https://arxiv.org/abs/2302.14838) (NeurIPS 2023)

Uses LLMs as adaptive mutation/crossover operators for neural architecture search:

- Replaces traditional NAS search space with LLM vocabulary
- Combines evolutionary prompt engineering with soft prompt-tuning
- LLM improves round-over-round through adaptation

**Key Results**:

- Novel CNN architectures outperforming human designs on MNIST-1D
- SOTA on 21/30 tasks in CLRS Algorithmic Reasoning Benchmark

---

### Many-Objective Grammar-Guided GP (MaOG3P)

**Paper**: [Enhancing Program Synthesis with Large Language Models Using Many-Objective Grammar-Guided Genetic Programming](https://www.mdpi.com/1999-4893/17/7/287) (Algorithms, 2024)

Combines LLMs with grammar-guided GP:

1. LLM generates initial code from task description
2. Code is mapped to BNF grammar-compliant program
3. Grammar-guided GP evolves with similarity to LLM solution as secondary objective

Addresses LLM struggles with complex syntax while leveraging their semantic understanding.

---

### Genetic Improvement of LLM-Generated Code

**Paper**: [Enhancing Large Language Models-Based Code Generation by Leveraging Genetic Improvement](https://link.springer.com/chapter/10.1007/978-3-031-56957-9_7) (EuroGP 2024)

Uses evolutionary Genetic Improvement to refine LLM-generated code using test cases. Demonstrates that combining LLMs with evolutionary post-processing yields better results than either alone.

---

## Optimization & Black-Box Search

### Large Language Models as Optimizers (OPRO)
**Paper**: [Large Language Models as Optimizers](https://arxiv.org/pdf/2309.03409) (ICLR 2024)
Proposes "Optimization by PROmpting," where the LLM iteratively generates new solutions from the natural language history of past solutions and their scores, effectively treating the LLM as the optimizer itself.

### Language Model Crossover (LMX)
**Paper**: [Language Model Crossover: Variation through Few-Shot Prompting](https://arxiv.org/pdf/2302.12170) (2023)
Introduces a variation operator based on few-shot prompting to semantically "crossover" parent strings via an LLM, showing strong performance in text-based evolutionary tasks.

### EvoLLM
**Paper**: [Large Language Models As Evolution Strategies](https://arxiv.org/pdf/2402.18381) (2024)
Explores using LLMs to replace traditional Gaussian mutation and crossover operators in Evolution Strategies (ES) for black-box optimization tasks.

### Quality-Diversity through AI Feedback (QDAIF)
**Paper**: [Quality-Diversity through AI Feedback](https://arxiv.org/pdf/2310.13032v4) (NeurIPS Workshop 2023)
Replaces the human or simulator in Quality-Diversity search with an AI model (like an LLM or VLM) to evaluate both the "quality" and "diversity" of creative artifacts.

### OptiMUS
**Paper**: [OptiMUS: Optimization Modeling Using MIP Solvers and Large Language Models](https://arxiv.org/pdf/2310.06116) (2023)
Combines LLMs with mixed-integer programming (MIP) solvers, where the LLM formulates the optimization model from natural language and the solver finds the optimal solution.

---

## Prompt Evolution

### Promptbreeder
**Paper**: [Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution](https://arxiv.org/pdf/2309.16797) (2023)
A self-improving system that evolves both the task-prompts and the "mutation-prompts" that modify them, enabling an open-ended evolutionary loop for prompt optimization.

### EvoPrompt
**Paper**: [Connecting Large Language Models with Evolutionary Algorithms Yields Powerful Prompt Optimizers](https://arxiv.org/pdf/2309.08532) (ICLR 2024)
Connects LLMs with evolutionary algorithms to optimize discrete prompts by generating a population of candidate prompts and evolving them based on performance metrics.

### Genetic Prompt Search (GPS)
**Paper**: [GPS: Genetic Prompt Search for Efficient Few-shot Learning](https://arxiv.org/pdf/2210.17041) (EMNLP 2022)
Applies genetic algorithms to automatically search for high-performing few-shot prompts for classification tasks, outperforming manual engineering.

### GrIPS
**Paper**: [GrIPS: Gradient-free, Edit-based Instruction Search for Prompting Large Language Models](https://arxiv.org/pdf/2203.07281) (EACL 2023)
A gradient-free, edit-based search method for instructions that iteratively improves prompts by making character-level and word-level edits.

---

## Model Merging & Architecture Search

### Evolutionary Model Merge
**Paper**: [Evolutionary Optimization of Model Merging Recipes](https://www.nature.com/articles/s42256-024-00975-8) (Nature Machine Intelligence, 2025)
Applies evolutionary search to discover optimal "recipes" (weights and layer permutations) for merging multiple Large Language Models, significantly outperforming manual merging strategies.

### AutoBERT-Zero
**Paper**: [AutoBERT-Zero: Evolving BERT Backbone from Scratch](https://arxiv.org/pdf/2107.07445) (AAAI 2022)
Uses evolutionary search to discover effective BERT-like architectures from primitive operations without relying on human-designed backbones or heuristics.

### LiteTransformerSearch
**Paper**: [LiteTransformerSearch: Training-free Neural Architecture Search for Efficient Language Models](https://arxiv.org/pdf/2203.02094) (NeurIPS 2022)
A training-free neural architecture search method for efficient language models that estimates performance without full training.

---

## Reinforcement Learning & Reward Design

### Eureka
**Paper**: [Eureka: Human-Level Reward Design via Coding Large Language Models](https://arxiv.org/pdf/2310.12931) (ICLR 2024)
Uses Coding LLMs to evolutionary optimize reward functions for Reinforcement Learning, enabling agents to learn complex dexterous skills (like pen-spinning) that were previously unsolvable.

### OpenELM
**Paper**: [The OpenELM Library: Leveraging Progress in Language Models for Novel Evolutionary Algorithms](https://arxiv.org/pdf/2404.16906) (2024)
An open-source library that leverages LLMs for novel evolutionary algorithms, specifically focusing on code generation and maintaining diversity in the population.

### Evolution through Large Models (ELM)
**Paper**: [Evolution through Large Models](https://arxiv.org/pdf/2206.08896) (2022)
The precursor to OpenELM, demonstrating that LLMs can act as intelligent mutation operators in an open-ended evolutionary loop, generating increasingly complex programs.

---

## Self-Improving Systems

### SICA: Self-Improving Coding Agent (ICLR 2025)

**Paper**: [A Self-Improving Coding Agent](https://openreview.net/pdf?id=rShJCyLsOr) (ICLR 2025 Workshop)

An LLM coding agent that autonomously edits its own codebase to improve performance:

- **Meta Agent Loop**: Alternates between benchmarking and self-modification
- **Performance Gains**: 17% → 53% improvement on SWE-Bench Verified subset
- **Generalization**: Also improves on LiveCodeBench and synthetic benchmarks

Key insight: Self-improvement works especially well for "agentic" tasks where the base LLM benefits from additional structure and guidance.

---

### ALMA: Agentic Long-Term Memory Architecture (2025)

**Paper**: [ALMA: Agentic Long-Term Memory Architecture for LLM Agents](https://arxiv.org/abs/2505.20290)

ALMA focuses on durable, retrieval-friendly memory for autonomous agents:

- **Structured long-term memory**: Stores and organizes past agent experience for reuse across tasks
- **Memory-grounded reasoning**: Uses retrieved context to improve planning and reduce repeated mistakes
- **Agentic workflows**: Designed for multi-step autonomous settings where context must persist over long horizons

**Relevance to Genesis**:

- Complements Genesis meta-memory and archive mechanisms for cross-generation knowledge retention
- Useful reference for planned long-term memory integrations (for example, persistent strategy and failure memory)

---

### OpenR: Advanced Reasoning Framework

**Paper**: [OpenR: An Open Source Framework for Advanced Reasoning with Large Language Models](https://arxiv.org/abs/2410.09671) (2024)

**GitHub**: [openreasoner/openr](https://github.com/openreasoner/openr)

**Website**: [openreasoner.github.io](https://openreasoner.github.io/)

An open-source framework for advanced reasoning with LLMs, combining process supervision, reward models, and search strategies:

- **Process Supervision**: Automated process supervision (OmegaPRM) for improving mathematical reasoning
- **Reward Models**: Both discriminative PRM and generative reward model training
- **Search Strategies**: Greedy search, Best-of-N, Beam search, MCTS, rStar (mutual reasoning)
- **RL Training**: Online policy training with APPO, GRPO, TPPO algorithms
- **Test-time Scaling**: Systematic exploration of test-time computation vs model parameters

**Key Results**:

- Process reward models (Math-psa) outperform outcome-based verifiers
- MCTS-based search improves reasoning performance over greedy decoding
- Test-time compute scaling can be more effective than parameter scaling
- Open-source datasets and models for mathematical reasoning

**Applications**: Mathematical reasoning (MATH dataset), multi-step problem solving, self-verification.

---

### SAGA: Self-Adapting Goal-Evolving Agents (2024)

**Paper**: [SAGA: Autonomous Goal-Evolving Agents for Scientific Discovery](https://arxiv.org/html/2512.21782v1)

An autonomous system that evolves both solutions AND objectives through bi-level optimization:

- **Bi-Level Optimization**:
  - Inner loop: Optimize solutions for current objectives (similar to Genesis)
  - Outer loop: Evolve objectives themselves based on results and failure analysis
- **Four Agentic Modules**: Planner (goal decomposition), Implementer (code generation), Optimizer (solution search), Analyzer (reward hacking detection)
- **Three Autonomy Levels**: Co-pilot (human-guided), semi-pilot (human review), autopilot (fully autonomous)
- **Multi-Objective Balancing**: Dynamically reweights competing objectives to prevent reward hacking

**Key Results**:

- **Antibiotic Design**: Generated drug-like K. pneumoniae inhibitors balancing efficacy and synthesizability
- **Materials Science**: Designed permanent magnets and superhard materials validated by DFT calculations
- **DNA Design**: ~50% improvement over baselines for cell-type-specific enhancers
- **Chemical Engineering**: Automated discovery of practical constraints in process flowsheet design

**Relevance to Genesis**:

Genesis excels at the "inner loop" (evolving code for fixed objectives). SAGA's "outer loop" (objective evolution) addresses Genesis's limitation of static `evaluate.py` functions. Key opportunities:

1. **Dynamic Fitness Functions**: Detect reward hacking and evolve objectives automatically
2. **Modular Architecture**: SAGA's four-module design (Planner/Implementer/Optimizer/Analyzer) provides clean abstraction that could improve Genesis's structure
3. **Multi-Objective Optimization**: Track Pareto frontier instead of single `combined_score`
4. **Human-in-the-Loop**: Add intervention points for reviewing objective changes

See [`docs/saga_integration.md`](saga_integration.md) for detailed integration design and [`docs/modular_architecture.md`](modular_architecture.md) for proposed refactoring.

---

## Surveys and Reviews

### Evolutionary Computation in the Era of Large Language Models

**Paper**: [Survey and Roadmap](https://arxiv.org/abs/2401.10034) (IEEE TEVC, 2024)

**GitHub**: [wuxingyu-ai/LLM4EC](https://github.com/wuxingyu-ai/LLM4EC)

Comprehensive survey covering three research directions:

1. **LLM-Enhanced EA**: Using LLMs as evolution operators, leveraging domain knowledge
2. **EA-Enhanced LLM**: Using EAs for prompt optimization and neural architecture search
3. **Synergistic Applications**: Code generation, software engineering, text generation

Essential reading for understanding the full landscape of LLM+EA research.

---

### When Large Language Models Meet Evolutionary Algorithms

**Paper**: [Potential Enhancements and Challenges](https://spj.science.org/doi/10.34133/research.0646) (Research, 2024)

Explores how LLMs can enhance EAs and vice versa, with discussion of challenges including:

- Computational costs
- Evaluation reliability
- Benchmark contamination

---

## Benchmarks

### SWE-bench

**Paper**: [SWE-bench: Can Language Models Resolve Real-world Github Issues?](https://github.com/SWE-bench/SWE-bench) (ICLR 2024 Oral)

2,200+ real GitHub issues from 12 Python repositories. Models must generate patches to fix issues.

**2024-2025 Progress**:

| System | SWE-bench Verified |
|--------|-------------------|
| Claude 3.5 Sonnet | 49% |
| CodeStory Midwit Agent | 62% |
| Gemini 2.5 Pro | 63.8% |
| OpenAI o3 | 72% (reported) |

**Caveats**: Research found 32.67% of patches involve "solution leakage" (answer in issue description).

---

### LiveCodeBench

Contamination-free benchmark using problems from weekly coding contests (LeetCode, AtCoder, CodeForces) with release date tagging.

---

### CodeElo (2025)

Elo rating system for LLM code generation using Codeforces problems, similar to chess rankings.

---

## Open-Source Implementations

### OpenEvolve

**GitHub**: [codelion/openevolve](https://github.com/codelion/openevolve) | [algorithmicsuperintelligence/openevolve](https://github.com/algorithmicsuperintelligence/openevolve)

**PyPI**: `pip install openevolve`

Open-source implementation of AlphaEvolve. Features:

- Codebase-scale optimization (not just single functions)
- Multi-LLM support via LiteLLM
- Replicates AlphaEvolve circle packing results
- HotpotQA prompt optimization example (+23% accuracy)

---

### OptiLLM

**GitHub**: [codelion/optillm](https://github.com/codelion/optillm)

OpenAI API-compatible proxy implementing inference optimization strategies:

- **Prompt Optimization**: Few-shot learning, structured prompts
- **Model Selection**: Task-specific model routing
- **Inference Optimization**: Quantization, hardware acceleration
- **Decoding Techniques**: CoT decoding, entropy-based decoding
- **Mixture of Agents (MoA)**: Ensemble multiple models

Drop-in replacement for OpenAI API with automatic optimization.

---

### ShinkaEvolve

**GitHub**: [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve)

**License**: Apache-2.0

The upstream project Genesis is forked from. Features WebUI, examples, and multi-backend support. See the main Genesis documentation for usage.

---

### FunSearch

**GitHub**: [google-deepmind/funsearch](https://github.com/google-deepmind/funsearch)

Reference implementation of the FunSearch algorithm.

---

### AI Scientist

**GitHub**: [SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist)

Full pipeline for automated scientific research.

---

## Further Reading

### Resource Collections

- **LLM4EC**: [GitHub - wuxingyu-ai/LLM4EC](https://github.com/wuxingyu-ai/LLM4EC) - Curated papers at the intersection of LLMs and evolutionary computation
- **Papers With Code - Program Synthesis**: [paperswithcode.com/task/program-synthesis](https://paperswithcode.com/task/program-synthesis/latest)

### Related Topics

- **Automated Machine Learning (AutoML)**: Neural architecture search, hyperparameter optimization
- **Neuroevolution**: Evolving neural network weights and architectures
- **Program Repair**: Automated bug fixing using LLMs
- **Code Generation Benchmarks**: HumanEval, MBPP, CodeContests

---

## Citation

If you use Genesis in your research, please cite:

```bibtex
@software{genesis2025,
  title = {Genesis: LLM-Driven Program Evolution},
  author = {Pearse, George},
  year = {2025},
  url = {https://github.com/GeorgePearse/Genesis}
}
```

For the underlying ShinkaEvolve framework:

```bibtex
@article{shinkaevolve2025,
  title = {ShinkaEvolve: Towards Open-Ended and Sample-Efficient Program Evolution},
  author = {Sakana AI},
  year = {2025},
  journal = {arXiv preprint arXiv:2509.19349}
}
```
