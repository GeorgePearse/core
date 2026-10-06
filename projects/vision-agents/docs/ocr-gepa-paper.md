# Prompt-Optimized OCR for Production (Paper Summary)

**Paper**: "GEPA Shows OCR is Steerable for Business Document Pipelines"  
**Authors**: Greg Miller, Jon Slemp (Intrinsic Labs)  
**Date**: October 2025  
**Source**: https://www.intrinsic-labs.ai/research/ocr-gepa-v1.pdf

## Key Claim

OCR is **steerable via prompt optimization** in production settings, particularly for business workflows with recurring, family-similar documents (invoices, forms, utility bills). Frontier models are now intelligent enough to analyze their own failures and iteratively optimize their prompts.

## Results

| Model | Baseline | GEPA Optimized | Gain |
|-------|----------|----------------|------|
| Gemini 2.0 Flash | 86.1% | 89.7% | +3.6 |
| Gemini 2.5 Flash | 88.8% | 92.4% | +3.6 |
| Gemini 2.5 Pro | 91.5% | 94.8% | +3.3 |

Pareto frontier approached ~97% on structured subsets where document families are consistent.

## The Two-Stage Pipeline

```
Image → Markdown (vision stage)
    ↓
Markdown → JSON (language stage)
```

GEPA optimizes prompts for **both** stages, but gains concentrate differently:

- **Vision stage**: Gemini extracts text and coarse structure. GEPA *does* optimize this prompt (coverage rules, reading order, table formatting, checkbox handling) but gains are **marginal**. Bounded by scan quality — the model either sees the text or it doesn't. Prompting can't fix missed tokens or corrupt text.
- **Language stage**: LLM maps text to strict schema. **This is where GEPA helps most** — schema discipline, read-order, reconciliation policies, null handling. Policy and structure dominate here, making it highly steerable.

## How GEPA Works Here

1. **Seed and evaluate**: Start with initial prompt, run on validation slice, capture JSON diff metrics
2. **Reflect**: Pass execution traces + image URLs to GPT-5 reflection model. It analyzes failure clusters (omitted footers, totals misalignment, hallucinated values) and proposes edits
3. **Select**: Evaluate candidates, update Pareto frontier over accuracy and prompt complexity
4. **Iterate**: Until convergence or budget exhaustion

Key insight: GEPA effectively **"pre-computes" reasoning and policy into the prompt** — yielding a configuration that generalizes across future documents.

## The "Teachable Band"

They optimized on a curated subset:
- Documents with baseline accuracy **70-90%** (partial understanding but systematic errors)
- Invoices, receipts, multi-column forms with common failure modes

This avoids wasting compute on unsalvageable scans or trivially correct samples.

## What GEPA Learned (Qualitative)

The reflection model independently converged toward best-practice extraction policies. Interestingly, the final optimized prompt (shown in the paper) is for the **vision stage** (Image→Markdown) — GEPA evolved detailed rules even where gains were smaller:

- **Coverage**: "include everything visible", "preserve reading order"
- **Anti-hallucination**: "do not invent", "use `unreadable` for illegible text"
- **Schema discipline**: "each label/value on its own line", "use Markdown tables"
- **Layout fidelity**: "parse line items before totals", "keep captions adjacent to figures"

By the end, GEPA had written a **policy prompt** — a deterministic specification for reliable document transcription.

## Cross-Model Transfer

Prompts optimized on Gemini 2.0 Flash transferred **80-90% of gains** to 2.5 Flash and Pro.

This supports a cost-efficient pattern: **optimize once on a small model, deploy broadly**.

## When OCR is Steerable

Steerability is strongest when:
- Documents are **family-similar** (recurring vendor templates, forms)
- Output schema is **strict and validated**
- Policies (read-order, null handling, reconciliation) are **explicit**
- Perception quality is **reasonable** (not heavily degraded scans)

These conditions describe most enterprise pipelines.

## The Compounding Error Problem

Document pipelines are non-deterministic. Five stages at 90% each:

```
(0.9)^5 ≈ 0.59 end-to-end reliability
```

This makes prompt optimization valuable — small per-stage gains compound.

## Limitations

- Results specific to document OCR/structured extraction (not unconstrained generation)
- Prompts can overfit to document families — monitor for drift
- Severe perception defects (low-res, heavy artifacts) still dominate failure modes

## Architecture Pattern

> Stabilize perception with strong OCR backbones and preprocessing; then add a **reflective, prompt-optimized extraction head**. As models advance, the optimization layer captures capability gains without retraining.

## References

- [Implementation](https://github.com/Studio-Intrinsic/benchmarking-ocr-gepa)
- [Omni OCR Benchmark](https://github.com/getomni-ai/benchmark)
- [DSPy Framework](https://github.com/stanfordnlp/dspy)
- [GEPA Optimizer](https://github.com/gepa-ai/gepa)
