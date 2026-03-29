# Genesis Roadmap

## Vision

Genesis aims to be the universal framework for LLM-driven code evolution across any programming language, execution environment, and optimization objective.

---

## Current Language Support

| Language | Local | E2B (base) | E2B (custom) | Notes |
|----------|:-----:|:----------:|:------------:|-------|
| **Python** | ✅ | ✅ | ✅ | First-class support, all features |
| **Rust** | ✅ | ❌ | ✅ | Needs `rustc` in environment |
| **C++** | ✅ | ❌ | ✅ | Needs `g++` or `clang++` |
| **CUDA** | ⚠️ | ❌ | ❌ | Requires GPU + `nvcc` |
| **JavaScript/TypeScript** | ✅ | ✅ | ✅ | Node.js available in E2B base |

### Adding New Language Support

To evolve code in any language, you need:

1. **Compiler/Interpreter** in the execution environment
2. **Python evaluation wrapper** that:
   - Compiles the evolved code (if needed)
   - Runs it against test cases
   - Returns a numeric fitness score

See `examples/mask_to_seg_rust/` for a complete Rust example.

---

## Execution Backend Status

| Backend | Status | Parallelism | GPU Support | Best For |
|---------|:------:|:-----------:|:-----------:|----------|
| **Local** | ✅ Done | 1-4 jobs | If available | Development, testing |
| **E2B** | ✅ Done | ~50 jobs | ❌ No | Cloud parallel execution |
| **Modal** | 🔜 Planned | Unlimited | ✅ Yes | Serverless GPU |
| **Ray** | 💭 Idea | Unlimited | ✅ Yes | Distributed clusters |

---

## Planned Improvements

### High Priority

#### E2B Templates for Compiled Languages
- [ ] Pre-built E2B templates with common toolchains:
  - `genesis-rust` - Rust toolchain (rustc, cargo)
  - `genesis-cpp` - C++ toolchain (g++, clang++, cmake)
  - `genesis-go` - Go toolchain
  - `genesis-full` - All languages combined
- [ ] One-command template deployment
- [ ] Documentation for custom template creation

#### Modal Integration for GPU Code
- [ ] CUDA kernel evolution with GPU execution
- [ ] PyTorch/JAX model optimization
- [ ] Serverless GPU with automatic scaling
- [ ] Cost tracking and budget limits

#### Improved Rust Support
- [ ] Cargo project support (not just single-file rustc)
- [ ] Crate dependency management
- [ ] SIMD-aware optimization prompts
- [ ] Benchmark-driven fitness (criterion.rs integration)

### Medium Priority

#### User Experience & Observability
- [ ] **Terminal Dashboard (TUI)**: Build an interactive Terminal User Interface (TUI) using [Textual](https://textual.textualize.io/) or `rich.live` to monitor evolution progress, view genealogy trees, and inspect best programs directly in the console. This provides a high-quality "local UI" experience without needing to spin up a separate web server.
- [ ] **Unified Local Launcher**: Create a single command (e.g., `genesis dev`) that launches both the evolution runner and the WebUI in a coordinated way, automatically opening the browser and managing background processes for a seamless local development experience.
- [ ] **LLM-Driven Task Setup**: Add a feature in the UI to setup tasks by talking to an LLM, allowing users to describe their problem in natural language and have the system automatically generate the initial configuration and code scaffold.

#### Benchmarking & Meta-Optimization

##### Standardized Assessment
- [ ] **Benchmark Suite**: Develop a diverse set of canonical tasks (algorithmic, control, creative) to rigorously compare evolution strategies (e.g., standard evolutionary algorithms vs. LLM-driven evolution vs. FunSearch).
- [ ] **Comparative Metrics**: Track sample efficiency (fitness vs. evaluations), wall-clock time, and token cost to benchmark against baselines like random search or standard genetic algorithms.

##### Bayesian & Hybrid Optimization
- [ ] **Hyperparameter Tuning**: Integrate Bayesian Optimization (e.g., Ax/BoTorch) to automatically tune evolutionary hyperparameters (population size, mutation rate, temperature) or prompt strategies.
- [ ] **Meta-Guidance**: Explore using Bayesian Optimization to guide the evolutionary search itself, such as selecting optimal parents or dynamically adjusting the exploration-exploitation balance based on trajectory analysis.

#### Language-Specific LLM Optimization Hints
- [ ] **Rust**: Ownership/borrowing patterns, SIMD intrinsics, zero-copy
- [ ] **C++**: Template metaprogramming, cache optimization, vectorization
- [ ] **CUDA**: Warp efficiency, shared memory, occupancy optimization
- [ ] **Python**: NumPy vectorization, Cython hints, memory views

#### Multi-Language Project Evolution
- [ ] Python + Rust (PyO3 bindings)
- [ ] Python + C++ (pybind11)
- [ ] Evolve both sides of FFI boundaries
- [ ] Cross-language fitness evaluation

#### Enhanced Parallelism
- [ ] Adaptive `max_parallel_jobs` based on backend capacity
- [ ] Job priority queuing
- [ ] Preemption for higher-fitness candidates
- [ ] Distributed island model across backends

#### Prompt Engineering & Optimization
- [ ] **Automated Prompt Optimization (DSPy)**: Integrate [DSPy](https://github.com/stanfordnlp/dspy) to automatically optimize the system prompts and mutation instructions. This moves away from hand-crafted prompts to a systematic, compile-time optimization process that maximizes evolutionary success rates.
- [ ] **Reinforcement Learning (RL) Integration**: Implement RL loops to treat the LLM as an agent, rewarding successful mutations and penalizing regressions. This could involve techniques like PPO or GRPO (Group Relative Policy Optimization) to finetune the mutation operators on the fly based on the specific fitness landscape of the current problem.
    - **PPO (Proximal Policy Optimization)**: A stable policy gradient method that avoids large, destructive updates by clipping the objective function, making it safer for online fine-tuning of the mutation agent.
    - **GRPO (Group Relative Policy Optimization)**: An optimization technique that removes the need for a critic model by estimating baselines from a group of outputs, significantly reducing memory usage while maintaining performance in reasoning tasks.

#### Knowledge Retrieval & Vector Search
- [ ] **Qdrant Integration**: Integrate [Qdrant](https://qdrant.tech/) (or similar vector DB) to index the full history of evolved programs using code embeddings.
- [ ] **Semantic Parent Selection**: Enable selecting parents based on semantic similarity to a target description or to fill gaps in the embedding space (semantic novelty).
- [ ] **Cross-Island Retrieval**: Allow islands to query relevant solutions from other islands based on semantic relevance rather than just fitness, facilitating better cross-pollination.
- [ ] **Natural Language Code Search**: Enable users to search the solution archive using natural language queries (e.g., "find code that uses SIMD for matrix multiplication") via the WebUI.
- [ ] **Graph-Based Lineage Analysis**: Store the evolutionary tree in a graph database to enable complex lineage queries (e.g., "Find the common ancestor of all successful solutions" or "Visualize the mutation pathway that led to this specific optimization").
    - *Benefits*: Efficiently model and query the full ancestry, detect cycles, analyze mutation efficacy, and represent code structure dependencies.
    - *Options*: [Neo4j](https://neo4j.com/), [FalkorDB](https://www.falkordb.com/), [ArangoDB](https://www.arangodb.com/).
    - *Note*: While **Qdrant** is excellent for semantic similarity and dense retrieval (finding code with similar *meaning*), a graph store is better suited for structural and relational queries (finding code with specific *ancestry*). A hybrid approach using both is often ideal for a complete knowledge system.

### Future Exploration

#### Additional Languages
| Language | Use Case | Complexity |
|----------|----------|------------|
| **WebAssembly** | Browser-based evolution, portable binaries | Medium |
| **Go** | Systems programming, microservices | Easy |
| **Julia** | Scientific computing, differentiable programming | Medium |
| **Zig** | Systems programming with safety | Medium |
| **Mojo** | Python syntax + systems performance | Hard (new language) |
| **Haskell** | Functional algorithm optimization | Medium |

#### Advanced Features
- [ ] **Auto-vectorization verification** - Ensure SIMD is actually used
- [ ] **Formal verification integration** - Prove evolved code correctness
- [ ] **Energy-aware optimization** - Minimize power consumption
- [ ] **Hardware-specific tuning** - ARM vs x86, specific CPU features
- [ ] **Agent Collaboration** - Chat system using the ELM language for conversation and collaboration between agents working on the evolutionary tree
- [ ] **OptiLLM Integration** - Integrate [OptiLLM](https://github.com/algorithmicsuperintelligence/optillm) to improve LLM outputs with inference time compute strategies (CoT, Best-of-N, etc.)
- [ ] **AgentEx Integration** - Integrate [Scale AgentEx](https://github.com/scaleapi/scale-agentex) for automated experimentation and hyperparameter optimization of agent configurations
- [ ] **Letta Memory Integration** - Integrate [Letta](https://github.com/letta-ai/letta) as an alternative memory system for long-term state management and knowledge retention across evolution generations
- [ ] **Meta-Strategy Experimentation** - Enable automated experimentation across entirely different evolutionary strategies (e.g., comparing Island Model vs. MAP-Elites vs. FunSearch) to dynamically discover the optimal search strategy for a given problem domain
- [ ] **Advanced Search & Logging** - Implement a robust search engine and comprehensive logging system.
  
  **Proposed Architecture:**
  - **The Python Layer: `structlog`**: Replace standard logging to force key-value context (e.g., `run_id`, `generation`, `tokens_in`, `reasoning`) attached to every log line.
  - **Storage Tier A: JSONL (Default)**: Write to `evolution_events.jsonl` files in the results directory for human-readable, zero-infrastructure local logging.
  - **Storage Tier B: ClickHouse (Production)**: Use a sidecar process to batch ingest JSONL logs into ClickHouse for high-performance compression (10x-100x text compression) and instant SQL analytics on millions of log rows.
  - **Query Capability**: Enable SQL queries like `SELECT reasoning FROM genesis_logs WHERE reasoning ILIKE '%segmentation fault%'` to instantly find "what the LLMs are thinking" across massive evolutionary runs.




---

## Completed Milestones

- [x] Core evolution framework with island model
- [x] Local execution backend
- [x] E2B cloud sandbox support
- [x] E2B cloud sandbox integration
- [x] Python language support
- [x] Rust language support (single-file)
- [x] WebUI for experiment monitoring
- [x] Novelty search and diversity maintenance
- [x] Multi-LLM support (OpenAI, Anthropic, Google, DeepSeek)
- [x] Hydra configuration system

---

## Contributing

We welcome contributions! Priority areas:

1. **E2B templates** for compiled languages
2. **Modal backend** implementation
3. **Language-specific examples** and evaluators
4. **Documentation** improvements

See [developer_guide.md](developer_guide.md) for contribution guidelines.
