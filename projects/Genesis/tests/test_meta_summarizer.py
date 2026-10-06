from dataclasses import dataclass
import importlib.util
from pathlib import Path
import pytest

from genesis.database import Program

_SUMMARIZER_PATH = Path(__file__).resolve().parents[1] / "genesis" / "core" / "summarizer.py"
_SUMMARIZER_SPEC = importlib.util.spec_from_file_location("genesis.core.summarizer", _SUMMARIZER_PATH)
assert _SUMMARIZER_SPEC is not None and _SUMMARIZER_SPEC.loader is not None
_SUMMARIZER_MODULE = importlib.util.module_from_spec(_SUMMARIZER_SPEC)
_SUMMARIZER_SPEC.loader.exec_module(_SUMMARIZER_MODULE)
MetaSummarizer = _SUMMARIZER_MODULE.MetaSummarizer


@dataclass
class _DummyResponse:
    content: str | None
    cost: float = 0.0


class _DummyMetaLLM:
    def batch_kwargs_query(self, num_samples, msg, system_msg):
        assert num_samples == 3
        return [
            _DummyResponse(content="summary for gen1", cost=0.1),
            None,
            _DummyResponse(content="summary for gen3", cost=0.2),
        ]


def test_step1_preserves_program_index_alignment_with_missing_batch_responses():
    summarizer = MetaSummarizer(meta_llm_client=_DummyMetaLLM(), language="python")

    programs = [
        Program(
            id="p1",
            code="print(1)",
            generation=1,
            correct=True,
            metadata={"patch_name": "patch-one"},
        ),
        Program(
            id="p2",
            code="print(2)",
            generation=2,
            correct=False,
            metadata={"patch_name": "patch-two"},
        ),
        Program(
            id="p3",
            code="print(3)",
            generation=3,
            correct=True,
            metadata={"patch_name": "patch-three"},
        ),
    ]

    summary, total_cost = summarizer._step1_individual_summaries(programs)

    assert summary is not None
    assert total_cost == pytest.approx(0.3)

    # Ensure metadata matches the correct original programs (1 and 3),
    # even though generation 2 response was missing.
    assert "Generation 1 - Patch Name patch-one" in summary
    assert "Generation 3 - Patch Name patch-three" in summary
    assert "Generation 2 - Patch Name patch-two" not in summary
