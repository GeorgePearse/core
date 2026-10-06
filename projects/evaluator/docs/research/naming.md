# Package Naming Ideas

Organizing potential names for the AI configuration backtesting framework.

## Top Contenders

### codebacktest
- **Import:** `import codebacktest as cbt`
- **Philosophy:** Perfect parallel to finance backtesting; testing strategies against historical data
- **Strengths:**
  - Directly captures the backtesting concept
  - "Code" explicitly in name
  - Clear what it does
  - Follows financial markets analogy
- **Elevator pitch:** "Like backtesting trading strategies, but for code generation quality"

### codetest
- **Import:** `import codetest as ct`
- **Philosophy:** Dead simple, like pytest/unittest
- **Strengths:**
  - Minimal, memorable
  - Easy to say in meetings
  - Follows testing tool naming (pytest, unittest)
  - CLI: `codetest run --pr-history`
  - Badge: `codetest: 98% quality maintained`
- **Weaknesses:** Very generic, might get lost in search

### evaluator
- **Import:** `import evaluator as rc`
- **Philosophy:** "Retro" implies retrospective testing and historical PR analysis
- **Strengths:**
  - Modern sounding despite "retro"
  - Good verb form: "Let's evaluator this change"
  - Hints at historical analysis
  - Memorable and unique
- **Weaknesses:** Slightly cryptic for newcomers

### codeback
- **Import:** `import codeback as cb`
- **Philosophy:** Shorter, punchier version of codebacktest
- **Strengths:**
  - Short and punchy
  - Easy to type
  - Still captures backtesting concept
  - "Let's run codeback on this MCP change" sounds natural
- **Weaknesses:** Could be confused with "callback"

## Quality/Guard-Focused

### codeguard
- **Import:** `import codeguard as cg`
- **Strengths:** Guards code generation quality; protective connotation
- **Weaknesses:** Generic "guard" pattern (too many *guard packages)

### codegrade
- **Import:** `import codegrade as cg`
- **Strengths:** Grading/evaluating code quality; good double meaning with "upgrade"
- **Weaknesses:** Might imply gamification over rigor

### codecheck
- **Import:** `import codecheck as cc`
- **Strengths:** Simple, action-oriented
- **Weaknesses:** Too generic, doesn't capture the backtesting/regression aspect

### codefence
- **Import:** `import codefence as cf`
- **Strengths:** Fencing off bad changes; protective metaphor
- **Weaknesses:** Unclear what it actually does

## Historical/Regression-Focused

### coderegress
- **Import:** `import coderegress as cr`
- **Strengths:** Explicitly about regression testing
- **Weaknesses:** "Regress" has negative connotations

### codereplay
- **Import:** `import codereplay as crp`
- **Strengths:** Replaying historical PRs against new configs
- **Weaknesses:** Longer, less catchy

### codeproof
- **Import:** `import codeproof as cp`
- **Strengths:** "Proving" your changes don't degrade quality
- **Weaknesses:** Implies certainty (impossible with LLMs)

### codetrace
- **Import:** `import codetrace as ct`
- **Strengths:** Tracing quality changes through iterations
- **Weaknesses:** Vague, could mean debugging

## MCP/Agent-Specific

### mcptest
- **Import:** `import mcptest as mt`
- **Philosophy:** Dead simple, follows pattern of pytest
- **Strengths:**
  - Immediately clear it's for testing MCP configurations
  - Unix naming tradition (pytest, bandit)
  - Short, easy to type
- **Weaknesses:**
  - Limits scope to MCP (might want to expand later)
  - Less memorable

### agentreg
- **Import:** `import agentreg as ar`
- **Strengths:** Agent regression testing; short and punchy
- **Weaknesses:** Very cryptic, hard to pronounce

### backcoder
- **Import:** `import backcoder as bc`
- **Strengths:** Nice ring to it; "coder" implies focusing on generated code
- **Weaknesses:** Slightly awkward pronunciation

## Creative/Metaphorical

### codewind
- **Import:** `import codewind as cw`
- **Philosophy:** Like "tailwind/headwind" in finance, but for code generation
- **Strengths:** Clever parallel to finance
- **Weaknesses:** Too obscure, needs explanation

### genguard
- **Import:** `import genguard as gg`
- **Strengths:** Guards generation quality
- **Weaknesses:** "Gen" is getting overloaded; doesn't include "code"

### codex-canary
- **Import:** `import codex_canary as cc`
- **Philosophy:** Canary in coal mine for your code generation
- **Strengths:** Evocative metaphor
- **Weaknesses:** Vendor-specific (Codex); too long for import

### contextual
- **Import:** `import contextual as ctx`
- **Philosophy:** Play on "Model Context Protocol" and contextual testing
- **Weaknesses:** Too generic, could mean many things

## Decision Rubric

Rate potential names on:
- ✅ **Clarity:** Does it immediately communicate purpose?
- ✅ **Memorability:** Easy to remember and say aloud?
- ✅ **Import ergonomics:** Nice shorthand when imported?
- ✅ **Searchability:** Unique enough to own search results?
- ✅ **Scalability:** Works if tool expands beyond initial scope?
- ✅ **Badge-ability:** Looks good in README badges?

## Final Recommendation

**codebacktest** wins on:
- Perfect analogy to finance backtesting (conceptually rich)
- "Code" explicitly in name
- Clear purpose immediately visible
- Scales to other AI configuration types
- Good badge: `[![codebacktest](https://img.shields.io/badge/codebacktest-passing-green.svg)]`

**Backup:** **codetest** if you want maximum simplicity and pytest alignment
