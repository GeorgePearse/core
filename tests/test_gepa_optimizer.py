import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "gepa_optimizer",
    Path(__file__).resolve().parents[1] / "genesis/core/gepa_optimizer.py",
)
assert spec is not None and spec.loader is not None
gepa_optimizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gepa_optimizer)
GEPAStyleOptimizer = gepa_optimizer.GEPAStyleOptimizer


def test_gepa_collects_successful_traces_and_formats_fewshot():
    optimizer = GEPAStyleOptimizer(
        enabled=True,
        num_fewshot_traces=2,
        max_traces=10,
        min_improvement=0.1,
    )

    # Pull one candidate for prompt context (cold-start exploration path).
    ctx = optimizer.build_prompt_context()
    assert ctx["candidate_id"] == 0
    assert ctx["candidate_instruction"] is not None

    # Observe one successful mutation and one failed mutation.
    optimizer.observe_result(
        generation=3,
        parent_score=0.4,
        child_score=0.7,
        patch_type="diff",
        patch_name="vectorize-loop",
        patch_description="Reduced nested-loop overhead.",
        diff_summary={"edits": 2},
        candidate_id=ctx["candidate_id"],
        correct=True,
    )
    optimizer.observe_result(
        generation=4,
        parent_score=0.7,
        child_score=0.6,
        patch_type="full",
        patch_name="bad-rewrite",
        patch_description="Regression.",
        diff_summary={"edits": 12},
        candidate_id=ctx["candidate_id"],
        correct=True,
    )

    assert len(optimizer.traces) == 1
    next_ctx = optimizer.build_prompt_context()
    assert next_ctx["fewshot_examples"] is not None
    assert "Successful Trace 1" in next_ctx["fewshot_examples"]
    assert "vectorize-loop" in next_ctx["fewshot_examples"]
