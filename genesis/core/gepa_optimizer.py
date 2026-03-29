import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


DEFAULT_GEPA_CANDIDATE_INSTRUCTIONS = [
    "Prioritize algorithm-level improvements over cosmetic refactors.",
    "Keep edits minimal and verify invariants before introducing major changes.",
    "Use evaluator metrics to focus on the dominant bottleneck in this iteration.",
    "Prefer robust implementations that preserve correctness under edge cases.",
    "Leverage successful inspiration patterns, but adapt them to this codebase.",
]


@dataclass
class GEPATrace:
    generation: int
    parent_score: float
    child_score: float
    score_delta: float
    patch_type: str
    patch_name: str
    patch_description: str
    diff_summary: str
    candidate_id: Optional[int]
    candidate_instruction: Optional[str]


class GEPAStyleOptimizer:
    """Lightweight DSPy-inspired optimizer for prompt guidance and few-shot traces."""

    def __init__(
        self,
        enabled: bool = False,
        num_fewshot_traces: int = 3,
        max_traces: int = 64,
        min_improvement: float = 0.0,
        exploration_weight: float = 1.1,
        candidate_instructions: Optional[List[str]] = None,
    ):
        self.enabled = enabled
        self.num_fewshot_traces = max(0, num_fewshot_traces)
        self.max_traces = max(1, max_traces)
        self.min_improvement = min_improvement
        self.exploration_weight = max(0.0, exploration_weight)
        self.candidate_instructions = candidate_instructions or list(
            DEFAULT_GEPA_CANDIDATE_INSTRUCTIONS
        )
        self.total_trials = 0
        self.candidate_stats: Dict[int, Dict[str, float]] = {
            idx: {"trials": 0.0, "total_delta": 0.0}
            for idx in range(len(self.candidate_instructions))
        }
        self.traces: List[GEPATrace] = []

    def build_prompt_context(self) -> Dict[str, Any]:
        """Return dynamic instruction and learned mutation traces for prompting."""
        if not self.enabled or not self.candidate_instructions:
            return {
                "candidate_id": None,
                "candidate_instruction": None,
                "fewshot_examples": None,
            }

        candidate_id = self._select_candidate()
        candidate_instruction = self.candidate_instructions[candidate_id]
        fewshot_examples = self._format_fewshot_examples()
        return {
            "candidate_id": candidate_id,
            "candidate_instruction": candidate_instruction,
            "fewshot_examples": fewshot_examples,
        }

    def observe_result(
        self,
        generation: int,
        parent_score: float,
        child_score: float,
        patch_type: Optional[str],
        patch_name: Optional[str],
        patch_description: Optional[str],
        diff_summary: Any,
        candidate_id: Optional[int],
        correct: bool,
    ) -> None:
        """Consume one completed mutation result and update GEPA state."""
        if not self.enabled:
            return

        delta = child_score - parent_score
        if candidate_id is not None and candidate_id in self.candidate_stats:
            self.total_trials += 1
            self.candidate_stats[candidate_id]["trials"] += 1.0
            self.candidate_stats[candidate_id]["total_delta"] += delta

        if not correct or delta < self.min_improvement:
            return

        instruction = None
        if (
            candidate_id is not None
            and 0 <= candidate_id < len(self.candidate_instructions)
        ):
            instruction = self.candidate_instructions[candidate_id]

        trace = GEPATrace(
            generation=generation,
            parent_score=parent_score,
            child_score=child_score,
            score_delta=delta,
            patch_type=patch_type or "unknown",
            patch_name=patch_name or "",
            patch_description=patch_description or "",
            diff_summary=self._compact_diff_summary(diff_summary),
            candidate_id=candidate_id,
            candidate_instruction=instruction,
        )
        self.traces.append(trace)
        self.traces.sort(key=lambda x: x.score_delta, reverse=True)
        if len(self.traces) > self.max_traces:
            self.traces = self.traces[: self.max_traces]

    def save_state(self, path: str) -> None:
        if not self.enabled:
            return
        payload = {
            "enabled": self.enabled,
            "num_fewshot_traces": self.num_fewshot_traces,
            "max_traces": self.max_traces,
            "min_improvement": self.min_improvement,
            "exploration_weight": self.exploration_weight,
            "candidate_instructions": self.candidate_instructions,
            "total_trials": self.total_trials,
            "candidate_stats": self.candidate_stats,
            "traces": [asdict(t) for t in self.traces],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def load_state(self, path: str) -> bool:
        if not self.enabled:
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception:
            return False

        self.total_trials = int(payload.get("total_trials", 0))
        stats = payload.get("candidate_stats", {})
        for raw_key, value in stats.items():
            key = int(raw_key)
            if key in self.candidate_stats and isinstance(value, dict):
                self.candidate_stats[key]["trials"] = float(value.get("trials", 0.0))
                self.candidate_stats[key]["total_delta"] = float(
                    value.get("total_delta", 0.0)
                )

        self.traces = []
        for item in payload.get("traces", []):
            try:
                self.traces.append(GEPATrace(**item))
            except TypeError:
                continue
        self.traces.sort(key=lambda x: x.score_delta, reverse=True)
        if len(self.traces) > self.max_traces:
            self.traces = self.traces[: self.max_traces]
        return True

    def _select_candidate(self) -> int:
        for idx in range(len(self.candidate_instructions)):
            if self.candidate_stats[idx]["trials"] == 0:
                return idx

        best_idx = 0
        best_score = float("-inf")
        for idx in range(len(self.candidate_instructions)):
            trials = self.candidate_stats[idx]["trials"]
            total_delta = self.candidate_stats[idx]["total_delta"]
            avg_delta = total_delta / max(trials, 1.0)
            ucb_bonus = self.exploration_weight * math.sqrt(
                math.log(self.total_trials + 1.0) / max(trials, 1.0)
            )
            score = avg_delta + ucb_bonus
            if score > best_score:
                best_score = score
                best_idx = idx
        return best_idx

    def _format_fewshot_examples(self) -> Optional[str]:
        if self.num_fewshot_traces <= 0 or not self.traces:
            return None

        selected = self.traces[: self.num_fewshot_traces]
        lines: List[str] = []
        for idx, trace in enumerate(selected, start=1):
            lines.append(f"## Successful Trace {idx}")
            lines.append(f"- Generation: {trace.generation}")
            lines.append(f"- Score delta: {trace.score_delta:+.4f}")
            lines.append(f"- Mutation type: {trace.patch_type}")
            if trace.patch_name:
                lines.append(f"- Mutation name: {trace.patch_name}")
            if trace.patch_description:
                lines.append(f"- Why it helped: {trace.patch_description}")
            if trace.diff_summary:
                lines.append(f"- Key edit summary: {trace.diff_summary}")
            if trace.candidate_instruction:
                lines.append(f"- Guidance used: {trace.candidate_instruction}")
            lines.append("")
        return "\n".join(lines).strip()

    def _compact_diff_summary(self, diff_summary: Any) -> str:
        if diff_summary is None:
            return ""
        if isinstance(diff_summary, dict):
            parts = []
            for key, value in diff_summary.items():
                parts.append(f"{key}={value}")
            return ", ".join(parts)[:500]
        return str(diff_summary)[:500]
