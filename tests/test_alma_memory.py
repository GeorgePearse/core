import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "alma_memory",
    Path(__file__).resolve().parents[1] / "genesis/core/alma_memory.py",
)
assert spec is not None and spec.loader is not None
alma_memory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alma_memory)
ALMAMemorySystem = alma_memory.ALMAMemorySystem


def test_alma_memory_retrieves_success_and_failure_context():
    memory = ALMAMemorySystem(
        enabled=True,
        max_entries=20,
        max_retrievals=3,
        min_success_delta=0.05,
    )

    memory.observe_outcome(
        generation=3,
        parent_score=0.40,
        child_score=0.65,
        correct=True,
        patch_type="diff",
        patch_name="vectorize-neighbor-loop",
        patch_description="Vectorized distance computation loop.",
        diff_summary={"edits": 3, "lines_added": 18},
        text_feedback="Good speedup in neighbor expansion.",
        error_message="",
    )
    memory.observe_outcome(
        generation=4,
        parent_score=0.65,
        child_score=0.20,
        correct=False,
        patch_type="full",
        patch_name="unsafe-rewrite",
        patch_description="Large rewrite introduced bug.",
        diff_summary={"edits": 20, "lines_removed": 150},
        text_feedback="Regression in correctness.",
        error_message="IndexError in hot loop",
    )

    ctx = memory.build_prompt_context(
        current_generation=5,
        parent_code="def neighbor_loop():\n    # vectorize neighbor compute\n    pass",
        parent_feedback="Need speed improvements without regressions.",
    )
    assert ctx is not None
    assert "ALMA Long-Term Memory" in ctx
    assert "Reuse These Successful Patterns" in ctx
    assert "Avoid These Failure Patterns" in ctx


def test_alma_memory_state_roundtrip(tmp_path):
    state_path = tmp_path / "alma_state.json"
    writer = ALMAMemorySystem(enabled=True, max_entries=10, max_retrievals=2)
    writer.observe_outcome(
        generation=1,
        parent_score=0.1,
        child_score=0.3,
        correct=True,
        patch_type="diff",
        patch_name="small-fix",
        patch_description="Improved bounds checks.",
        diff_summary={"edits": 1},
        text_feedback="Stable behavior.",
        error_message="",
    )
    writer.save_state(str(state_path))

    reader = ALMAMemorySystem(enabled=True, max_entries=10, max_retrievals=2)
    assert reader.load_state(str(state_path))
    assert len(reader.entries) == 1
    assert reader.entries[0].patch_name == "small-fix"
