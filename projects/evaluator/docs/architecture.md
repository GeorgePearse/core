# Architecture

Retrocode is a backtesting framework for AI agent instructions. It validates that an AI agent, when given a specific set of instructions (e.g., `CLAUDE.md`), performs tasks according to those rules.

## Core Design

The system follows a pipeline architecture:

```mermaid
graph TD
    A[YAML Test Files] -->|Parser| B[TestSuite Objects]
    B -->|Runner| C[Executor]
    C -->|Local| D[Local Environment]
    C -->|E2B| E[E2B Sandbox]
    D --> F[Agent Response]
    E --> F
    F -->|Evaluator| G[Assertions]
    G -->|Reporter| H[Results (MD/HTML)]
```

## Components

### 1. Test Definition (YAML)
Tests are defined in declarative YAML files.
- **Location**: `tests/backtests/*.backtest.yaml`
- **Schema**: Defined in `evaluator.models.TestSuite` and `TestCase`

### 2. Parser (`evaluator.parser`)
- **Responsibility**: validating and loading YAML files into Pydantic models.
- **Features**: 
  - Validates schema structure
  - Resolves file paths (e.g., instruction files)

### 3. Executors (`evaluator.executors`)
The executor is responsible for running the agent code in a specific environment.

#### Local Executor (`LocalExecutor`)
- Runs the agent directly in the current process/environment.
- **Pros**: Fast, no setup.
- **Cons**: No isolation, agent can modify local files, shares dependencies.

#### E2B Executor (`E2BExecutor`)
- Runs the agent in an isolated cloud sandbox using [E2B](https://e2b.dev).
- **Process**:
  1. **Template**: Builds or reuses a Docker-based template (e.g., `base`, `claude-tools`).
  2. **Session**: Acquires a sandbox session.
  3. **Setup**: Injects environment variables (API keys) and uploads instruction files.
  4. **Execution**: Runs a Python script inside the sandbox that invokes the agent.
  5. **Output**: Captures structured JSON output from the sandbox.
- **Pros**: Full isolation, reproducible environment, security.

### 4. Agent Invoker (`evaluator.agent`)
- Wraps the LLM interaction (currently Anthropic Claude).
- Constructs the prompt with:
  - System prompt (from instruction file)
  - User task
- Returns structured `AgentResponse` containing:
  - Full text response
  - Extracted code blocks
  - Tool calls
  - Generated shell commands

### 5. Assertions (`evaluator.assertions`)
Evaluators check the `AgentResponse` against defined rules.

| Type | Evaluator Class | Description |
|------|-----------------|-------------|
| `must_contain` | `MustContainEvaluator` | Checks for substring presence |
| `must_not_contain` | `MustNotContainEvaluator` | Checks for substring absence |
| `regex_match` | `RegexMatchEvaluator` | Matches regex patterns |
| `json_schema` | `JSONSchemaEvaluator` | Validates JSON structure |
| `code_contains` | `CodeContainsEvaluator` | Checks if code snippet exists (AST/Exact) |
| `code_excludes` | `CodeExcludesEvaluator` | Checks if code patterns are absent |
| `llm_judge` | `LLMJudgeEvaluator` | Uses an LLM to evaluate complex criteria |
| `snapshot` | `SnapshotEvaluator` | Compares output against saved snapshot |

### 6. Reporting (`evaluator.reporting`)
Generates human-readable reports from `TestResult` objects.
- **Markdown**: For CLI output and simple logs.
- **HTML**: For detailed, interactive reports.

## Data Flow

1. **CLI** (`evaluator.cli`) receives command to run tests.
2. **Parser** reads YAML files and creates `TestSuite` objects.
3. **TestRunner** iterates through test cases.
4. **Executor** runs the agent for each test case:
   - Sets up environment (Local or E2B).
   - Invokes Agent.
   - Captures output.
5. **AssertionRegistry** dispatches assertions to specific evaluators.
6. **Results** are collected and passed to **Reporters**.
7. Final report is saved to disk.
