"""Offline active-learning harness for instance-segmentation annotation efficiency.

This script simulates a budgeted human-in-the-loop process:
1. A Critic scores object-level uncertainty/risk.
2. A QueryPolicy selects which objects to query under hard budget constraints.
3. Queried objects become "learned", reducing future error on similar objects.
4. Performance-vs-cost points are emitted for plotting.

Input is a JSONL file with one frame per line:
{
  "frame_id": "frame-001",
  "objects": [
    {"object_id": "o1", "class_name": "wire", "difficulty": 0.8},
    {"object_id": "o2", "class_name": "beam", "difficulty": 0.3}
  ]
}
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dspy


@dataclass(frozen=True)
class ObjectExample:
    object_id: str
    class_name: str
    difficulty: float


@dataclass(frozen=True)
class FrameExample:
    frame_id: str
    objects: list[ObjectExample]


class CriticSignature(dspy.Signature):
    """Estimate per-object risk score for needing human correction."""

    object_json: str = dspy.InputField(desc="JSON object metadata including class_name and difficulty.")
    budget_left: int = dspy.InputField(desc="Remaining query budget in this run.")
    frame_budget_left: int = dspy.InputField(desc="Remaining per-frame budget.")
    risk_score: float = dspy.OutputField(desc="Risk score in [0,1], higher means more likely wrong.")
    critique: str = dspy.OutputField(desc="Short reason for the assigned risk.")


class QueryPolicySignature(dspy.Signature):
    """Select object ids to query under hard constraints."""

    frame_id: str = dspy.InputField(desc="Frame id under consideration.")
    candidates_json: str = dspy.InputField(desc="JSON list with object_id + risk_score entries.")
    max_queries_this_frame: int = dspy.InputField(desc="Maximum allowed queries for this frame.")
    budget_left: int = dspy.InputField(desc="Remaining global query budget.")
    selected_object_ids_csv: str = dspy.OutputField(desc="Comma-separated object ids to query now.")


class CriticModule(dspy.Module):
    """DSPy critic with deterministic fallback when no LM is configured."""

    def __init__(self) -> None:
        super().__init__()
        self.predictor = dspy.Predict(CriticSignature)

    def forward(self, object_json: str, budget_left: int, frame_budget_left: int) -> dspy.Prediction:
        if dspy.settings.lm is None:
            payload = json.loads(object_json)
            difficulty = float(payload.get("difficulty", 0.5))
            return dspy.Prediction(risk_score=max(0.0, min(1.0, difficulty)), critique="difficulty heuristic")
        return self.predictor(object_json=object_json, budget_left=budget_left, frame_budget_left=frame_budget_left)


class QueryPolicyModule(dspy.Module):
    """DSPy query policy with deterministic fallback when no LM is configured."""

    def __init__(self) -> None:
        super().__init__()
        self.predictor = dspy.Predict(QueryPolicySignature)

    def forward(self, frame_id: str, candidates_json: str, max_queries_this_frame: int, budget_left: int) -> dspy.Prediction:
        if dspy.settings.lm is None:
            candidates = json.loads(candidates_json)
            ranked = sorted(candidates, key=lambda c: float(c["risk_score"]), reverse=True)
            k = max(0, min(max_queries_this_frame, budget_left))
            chosen = [str(item["object_id"]) for item in ranked[:k]]
            return dspy.Prediction(selected_object_ids_csv=",".join(chosen))
        return self.predictor(
            frame_id=frame_id,
            candidates_json=candidates_json,
            max_queries_this_frame=max_queries_this_frame,
            budget_left=budget_left,
        )


@dataclass
class SimulationState:
    learned_object_ids: set[str]


def _load_frames(path: Path) -> list[FrameExample]:
    frames: list[FrameExample] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            objects = [
                ObjectExample(
                    object_id=str(obj["object_id"]),
                    class_name=str(obj.get("class_name", "unknown")),
                    difficulty=float(obj.get("difficulty", 0.5)),
                )
                for obj in row.get("objects", [])
            ]
            frames.append(FrameExample(frame_id=str(row["frame_id"]), objects=objects))
    return frames


def _error_probability(obj: ObjectExample, state: SimulationState) -> float:
    base = max(0.02, min(0.98, obj.difficulty))
    if obj.object_id in state.learned_object_ids:
        return max(0.01, base * 0.35)
    return base


def _performance(frames: list[FrameExample], state: SimulationState) -> float:
    probs: list[float] = []
    for frame in frames:
        for obj in frame.objects:
            probs.append(_error_probability(obj, state))
    if not probs:
        return 1.0
    return 1.0 - (sum(probs) / len(probs))


def _parse_selected_ids(csv_text: str) -> list[str]:
    return [item.strip() for item in csv_text.split(",") if item.strip()]


def _optimize_modules_if_possible(
    critic: CriticModule,
    policy: QueryPolicyModule,
    trainset: list[dspy.Example],
) -> tuple[CriticModule, QueryPolicyModule]:
    try:
        from dspy.teleprompt import BootstrapFewShot
    except Exception:
        return critic, policy
    if dspy.settings.lm is None or not trainset:
        return critic, policy

    metric = lambda _example, _pred, _trace=None: 1.0
    optimizer = BootstrapFewShot(metric=metric, max_bootstrapped_demos=4, max_labeled_demos=8)
    optimized_critic = optimizer.compile(critic, trainset=trainset)
    optimized_policy = optimizer.compile(policy, trainset=trainset)
    return optimized_critic, optimized_policy


def run_simulation(
    frames: list[FrameExample],
    max_queries_per_frame: int,
    max_queries_total: int,
    budget_step: int,
    optimize_prompts: bool,
) -> list[dict[str, Any]]:
    critic = CriticModule()
    policy = QueryPolicyModule()

    if optimize_prompts:
        trainset: list[dspy.Example] = []
        for frame in frames[: min(20, len(frames))]:
            for obj in frame.objects[:5]:
                trainset.append(
                    dspy.Example(
                        object_json=json.dumps({"class_name": obj.class_name, "difficulty": obj.difficulty}),
                        budget_left=max_queries_total,
                        frame_budget_left=max_queries_per_frame,
                        risk_score=obj.difficulty,
                        critique="higher difficulty implies higher risk",
                    ).with_inputs("object_json", "budget_left", "frame_budget_left")
                )
        critic, policy = _optimize_modules_if_possible(critic, policy, trainset)

    rows: list[dict[str, Any]] = []
    for budget in range(0, max_queries_total + 1, budget_step):
        state = SimulationState(learned_object_ids=set())
        remaining = budget
        queried = 0

        for frame in frames:
            if remaining <= 0:
                break
            frame_cap = min(max_queries_per_frame, remaining)
            if frame_cap <= 0:
                continue

            candidates: list[dict[str, Any]] = []
            for obj in frame.objects:
                object_json = json.dumps({"object_id": obj.object_id, "class_name": obj.class_name, "difficulty": obj.difficulty})
                pred = critic(object_json=object_json, budget_left=remaining, frame_budget_left=frame_cap)
                candidates.append(
                    {
                        "object_id": obj.object_id,
                        "risk_score": float(getattr(pred, "risk_score", obj.difficulty)),
                    }
                )

            policy_pred = policy(
                frame_id=frame.frame_id,
                candidates_json=json.dumps(candidates),
                max_queries_this_frame=frame_cap,
                budget_left=remaining,
            )
            selected = _parse_selected_ids(str(getattr(policy_pred, "selected_object_ids_csv", "")))
            selected = selected[:frame_cap]
            for object_id in selected:
                if remaining <= 0:
                    break
                state.learned_object_ids.add(object_id)
                remaining -= 1
                queried += 1

        perf = _performance(frames, state)
        gain_per_cost = perf / queried if queried > 0 else perf
        rows.append(
            {
                "budget": budget,
                "queried_objects": queried,
                "performance": round(perf, 6),
                "quality_gain_per_annotation": round(gain_per_cost, 6),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DSPy active-learning curve simulation for instance segmentation.")
    parser.add_argument("--input-jsonl", required=True, help="Path to frame/object JSONL input.")
    parser.add_argument("--output-csv", required=True, help="Where to write performance-vs-cost CSV.")
    parser.add_argument("--output-plot", default=None, help="Optional PNG path for X(objects queried) vs Y(performance) plot.")
    parser.add_argument("--max-queries-per-frame", type=int, default=2, help="Hard cap of annotation queries per frame.")
    parser.add_argument("--max-queries-total", type=int, default=200, help="Hard cap of annotation queries per run.")
    parser.add_argument("--budget-step", type=int, default=10, help="Budget step for curve points.")
    parser.add_argument("--optimize-prompts", action="store_true", help="Try DSPy prompt optimization for Critic/QueryPolicy.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_csv)
    frames = _load_frames(input_path)
    rows = run_simulation(
        frames=frames,
        max_queries_per_frame=args.max_queries_per_frame,
        max_queries_total=args.max_queries_total,
        budget_step=max(1, args.budget_step),
        optimize_prompts=bool(args.optimize_prompts),
    )
    _write_csv(output_path, rows)
    if args.output_plot:
        try:
            import matplotlib.pyplot as plt

            xs = [int(row["queried_objects"]) for row in rows]
            ys = [float(row["performance"]) for row in rows]
            plt.figure(figsize=(8, 5))
            plt.plot(xs, ys, marker="o")
            plt.xlabel("Queried Objects (Human Inputs)")
            plt.ylabel("Performance")
            plt.title("Active Learning Curve")
            plt.grid(True, alpha=0.3)
            plot_path = Path(args.output_plot)
            plot_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(plot_path, dpi=140, bbox_inches="tight")
            plt.close()
            print(f"Wrote plot to {plot_path}")
        except Exception as exc:
            print(f"Plot generation skipped: {exc}")
    print(f"Wrote {len(rows)} curve points to {output_path}")


if __name__ == "__main__":
    main()
