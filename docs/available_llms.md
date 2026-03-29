# Available LLMs in Genesis

Genesis supports a wide range of Large Language Models from multiple providers with automatic cycling and dynamic selection capabilities.

## Supported Providers

Genesis integrates with 4 major LLM providers via unified API:

1. **Anthropic Claude** (via Anthropic API)
2. **OpenAI GPT** (via OpenAI API)
3. **Google Gemini** (via OpenAI-compatible API)
4. **DeepSeek** (via OpenAI-compatible API)
5. **AWS Bedrock** (via AnthropicBedrock API)
6. **Azure OpenAI** (via Azure API)

---

## Available Models

### Anthropic Claude Models

| Model | Input Price | Output Price | Best For |
|-------|-------------|--------------|----------|
| `claude-3-5-haiku-20241022` | $0.80/M | $4.00/M | Fast, lightweight tasks |
| `claude-3-5-sonnet-20241022` | $3.00/M | $15.00/M | Balanced performance |
| `claude-3-5-sonnet-latest` | $3.00/M | $15.00/M | Latest Sonnet version |
| `claude-3-opus-20240229` | $15.00/M | $75.00/M | Most capable |
| `claude-3-7-sonnet-20250219` | $3.00/M | $15.00/M | Extended thinking (reasoning) |
| `claude-4-sonnet-20250514` | $3.00/M | $15.00/M | Claude 4 with reasoning |
| `claude-sonnet-4-5-20250929` | $3.00/M | $15.00/M | Latest reasoning model |

**Features:**
- Extended thinking mode for reasoning models
- Native structured output (not yet implemented)
- High context windows (200K+ tokens)

---

### OpenAI GPT Models

| Model | Input Price | Output Price | Best For |
|-------|-------------|--------------|----------|
| `gpt-4o-mini` | $0.15/M | $0.60/M | Fastest, cheapest |
| `gpt-4o-mini-2024-07-18` | $0.15/M | $0.60/M | Specific mini version |
| `gpt-4o-2024-08-06` | $2.50/M | $10.00/M | General purpose |
| `gpt-4.1` | $2.00/M | $8.00/M | Latest GPT-4 series |
| `gpt-4.1-2025-04-14` | $2.00/M | $8.00/M | Specific 4.1 version |
| `gpt-4.1-mini` | $0.40/M | $1.60/M | Lightweight 4.1 |
| `gpt-4.1-nano` | $0.10/M | $1.40/M | Ultra lightweight |
| `gpt-4.5-preview-2025-02-27` | $75.00/M | $150.00/M | Most advanced (preview) |
| **Reasoning Models:** | | | |
| `o1-2024-12-17` | $15.00/M | $60.00/M | Deep reasoning |
| `o3-mini` | $1.10/M | $4.40/M | Efficient reasoning |
| `o3-mini-2025-01-31` | $1.10/M | $4.40/M | Reasoning mini |
| `o3-2025-04-16` | $10.00/M | $40.00/M | Advanced reasoning |
| `o4-mini` | $1.10/M | $4.40/M | Latest mini reasoning |
| **GPT-5 Series (Hypothetical):** | | | |
| `gpt-5` | $1.25/M | $10.00/M | Next generation |
| `gpt-5-mini` | $0.25/M | $2.00/M | Next gen mini |
| `gpt-5-nano` | $0.05/M | $0.40/M | Next gen nano |
| `gpt-5.1` | $1.25/M | $10.00/M | Future version |

**Features:**
- Reasoning models with chain-of-thought
- Structured output support
- Function calling
- Vision capabilities (not used in Genesis)

---

### DeepSeek Models

| Model | Input Price | Output Price | Best For |
|-------|-------------|--------------|----------|
| `deepseek-chat` | $0.27/M | $1.10/M | General chat, very cheap |
| `deepseek-reasoner` | $0.55/M | $2.19/M | Reasoning tasks, cost-effective |

**Features:**
- Most cost-effective models
- Native reasoning support
- Great for code generation
- Chinese & English bilingual

---

### Google Gemini Models

| Model | Input Price | Output Price | Best For |
|-------|-------------|--------------|----------|
| `gemini-2.5-pro` | $1.25/M | $10.00/M | Most capable Gemini |
| `gemini-2.5-flash` | $0.30/M | $2.50/M | Fast, balanced |
| `gemini-2.5-flash-lite-preview-06-17` | $0.10/M | $0.40/M | Ultra-fast preview |
| `gemini-3-pro-preview` | $2.00/M | $12.00/M | Next generation (preview) |

**Features:**
- Long context (up to 1M tokens for some models)
- Multimodal (not used in Genesis)
- Native thinking mode
- Very competitive pricing

---

### AWS Bedrock Models

Access Anthropic models via AWS Bedrock:

| Model | Notes |
|-------|-------|
| `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` | Claude Sonnet via Bedrock |
| `bedrock/anthropic.claude-3-5-haiku-20241022-v1:0` | Claude Haiku via Bedrock |
| `bedrock/anthropic.claude-3-opus-20240229-v1:0` | Claude Opus via Bedrock |
| `bedrock/us.anthropic.claude-3-7-sonnet-20250219-v1:0` | Claude 3.7 Sonnet |
| `bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0` | Claude 4 Sonnet |

**Requirements:**
- AWS credentials in environment: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION_NAME`
- Same pricing as direct Anthropic API (may vary by region)

---

### Azure OpenAI Models

Access OpenAI models via Azure:

| Model Prefix | Example | Notes |
|--------------|---------|-------|
| `azure-*` | `azure-gpt-4.1`, `azure-o3-mini` | Prefix any OpenAI model with `azure-` |

**Requirements:**
- `AZURE_OPENAI_API_KEY`
- `AZURE_API_VERSION`
- `AZURE_API_ENDPOINT`

---

## Model Selection System

Genesis supports **3 modes** for model selection:

### 1. Static Single Model (Default)

Use one model for all mutations:

```yaml
evo_config:
  llm_models:
    - gpt-4.1
```

### 2. Static Multi-Model (Random Selection)

Randomly select from a list:

```yaml
evo_config:
  llm_models:
    - gpt-4.1
    - claude-3-5-sonnet-20241022
    - gemini-2.5-flash
```

Models are selected randomly with equal probability.

### 3. Dynamic Model Selection (UCB Bandit)

**Automatically learns** which models perform best and increases their usage:

```yaml
evo_config:
  llm_models:
    - gpt-4.1
    - gpt-4.1-mini
    - claude-3-5-sonnet-20241022
    - claude-3-5-haiku-20241022
    - gemini-2.5-flash
    - deepseek-chat
  llm_dynamic_selection: "ucb"  # Enable adaptive selection
  llm_dynamic_selection_kwargs:
    exploration_coef: 1.0       # Exploration vs exploitation
    epsilon: 0.2                 # Random exploration rate
    auto_decay: 0.95             # Decay old observations
```

**How it works:**
1. **Initial Phase**: All models tried equally
2. **Learning Phase**: Models producing better offspring get higher selection probability
3. **Exploitation Phase**: Best-performing models used more frequently
4. **Continuous Adaptation**: Keeps exploring to find better models

**Algorithm: Asymmetric UCB (Upper Confidence Bound)**
- Tracks mean reward per model
- Adds confidence bonus for exploration
- Shifts rewards relative to baseline/parent fitness
- Adapts to changing distributions

**Benefits:**
- Automatically finds best models for your task
- Balances cost vs performance
- Adapts as evolution progresses
- No manual tuning needed

---

## Configuration Examples

### Cost-Optimized Setup

```yaml
evo_config:
  llm_models:
    - gpt-4o-mini        # $0.15/M input
    - deepseek-chat      # $0.27/M input
    - gemini-2.5-flash-lite-preview-06-17  # $0.10/M input
  llm_dynamic_selection: "ucb"
```

### Performance-Optimized Setup

```yaml
evo_config:
  llm_models:
    - claude-3-5-sonnet-20241022
    - gpt-4.1
    - gemini-2.5-pro
  llm_dynamic_selection: "ucb"
```

### Reasoning-Focused Setup

```yaml
evo_config:
  llm_models:
    - o3-mini-2025-01-31
    - claude-3-7-sonnet-20250219
    - deepseek-reasoner
    - gemini-2.5-pro
  llm_dynamic_selection: "ucb"
```

### Cost-Performance Balanced

```yaml
evo_config:
  llm_models:
    - gpt-4.1-mini       # Good balance
    - claude-3-5-haiku-20241022
    - gemini-2.5-flash
    - deepseek-chat
  llm_dynamic_selection: "ucb"
```

---

## Environment Variables

Set these in your `.env` file:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# DeepSeek
DEEPSEEK_API_KEY=sk-...

# Gemini
GEMINI_API_KEY=AIzaSy...

# Azure OpenAI
AZURE_OPENAI_API_KEY=...
AZURE_API_VERSION=2024-02-15-preview
AZURE_API_ENDPOINT=https://your-resource.openai.azure.com/

# AWS Bedrock
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION_NAME=us-east-1
```

---

## Model Selection Monitoring

When using dynamic selection, Genesis logs model performance:

```
AsymmetricUCB Summary:
arm                       n    mean  exploit  explore  score    post
gpt-4.1                   5   0.850   0.850    0.120   0.970   0.45
claude-3-5-sonnet         3   0.820   0.820    0.156   0.976   0.35
gemini-2.5-flash          2   0.750   0.750   0.189   0.939   0.15
deepseek-chat             1   0.700   0.700   0.268   0.968   0.05
```

- **n**: Number of times used
- **mean**: Average normalized reward
- **exploit**: Exploitation component (mean fitness)
- **explore**: Exploration bonus (uncertainty)
- **score**: Combined UCB score (exploit + explore)
- **post**: Selection probability for next iteration

---

## Cost Tracking

Genesis tracks costs per model in ClickHouse:

```sql
SELECT 
    model,
    count() as calls,
    sum(cost) as total_cost,
    avg(cost) as avg_cost_per_call
FROM llm_logs
GROUP BY model
ORDER BY total_cost DESC;
```

---

## Recommendations

### For Research/Experiments
- Use dynamic selection with diverse models
- Include both fast and capable models
- Monitor costs via ClickHouse

### For Production
- Start with dynamic selection to find best model
- Once identified, switch to single best model
- Use cost-optimized models for large populations

### For Code Evolution
- Reasoning models (o-series, claude-3-7, deepseek-reasoner) often perform best
- Balance with faster models (mini/flash variants) for speed
- DeepSeek offers best cost-performance for code tasks

---

## Adding New Models

To add a new model:

1. **Add pricing to `genesis/llm/models/pricing.py`:**
   ```python
   OPENAI_MODELS = {
       "new-model-name": {
           "input_price": X / M,
           "output_price": Y / M,
       }
   }
   ```

2. **Add to appropriate provider function in `genesis/llm/models/`**

3. **Use in config:**
   ```yaml
   llm_models:
     - new-model-name
   ```

---

## Summary

✅ **60+ models** across 6 providers
✅ **Dynamic model selection** with UCB bandit algorithm
✅ **Cost tracking** and monitoring
✅ **Reasoning models** for complex tasks
✅ **Automatic adaptation** to find best models

Genesis provides unparalleled flexibility in LLM selection, allowing you to optimize for cost, performance, or automatically discover the best model for your specific evolutionary task.
