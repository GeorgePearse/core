"""TracingReAct: a dspy.ReAct subclass that emits reasoning trace events.

Each iteration of the ReAct loop produces a Thought, an Action (tool name + args),
and an Observation (tool result).  The stock dspy.ReAct stores these in a plain
trajectory dict but never surfaces them to the caller.  TracingReAct intercepts
every iteration and emits structured viewer events so the frontend can display
the agent's reasoning process in real time.
"""

from __future__ import annotations

from typing import Any, Callable

import dspy
from dspy.adapters.types.tool import Tool
from dspy.signatures.signature import ensure_signature
from loguru import logger

from agentic_vision.viewer_runtime import AgenticVisionRunRecorder


class TracingReAct(dspy.ReAct):
    """ReAct that emits Thought/Action/Observation events to a viewer recorder.

    Usage is identical to ``dspy.ReAct``; the extra ``viewer_recorder``
    parameter is stored per-forward-call so a single module instance can
    serve multiple concurrent runs.
    """

    def __init__(
        self,
        signature: type["dspy.Signature"],
        tools: list[Callable],
        max_iters: int = 20,
    ) -> None:
        super().__init__(signature, tools, max_iters)
        self._viewer_recorder: AgenticVisionRunRecorder | None = None

    def forward(self, **input_args: Any) -> dspy.Prediction:
        recorder = input_args.pop("viewer_recorder", None)
        self._viewer_recorder = recorder
        return super().forward(**input_args)

    # ------------------------------------------------------------------
    # The core interception: override the iteration loop
    # ------------------------------------------------------------------

    # We cannot easily override the loop inside dspy.ReAct.forward because
    # it is a single method.  Instead we monkey-patch at the tool-call
    # boundary.  The cleanest approach is to wrap every tool so that
    # *before* it runs we emit the Thought/Action event and *after* it
    # runs we emit the Observation event.
    #
    # However, dspy.ReAct.forward stores thought/tool_name/tool_args in
    # the trajectory *before* calling the tool, so we need access to those
    # values.  The simplest reliable hook is to override the entire forward
    # method with our own loop that mirrors the parent logic but adds
    # event emissions.

    def _run_react_loop(
        self,
        input_args: dict[str, Any],
        max_iters: int,
    ) -> tuple[dict[str, Any], dspy.Prediction | None]:
        """Execute the ReAct loop with viewer event emission.

        Returns (trajectory, react_prediction) so the caller can decide
        how to produce the final Prediction.
        """
        recorder = self._viewer_recorder
        trajectory: dict[str, Any] = {}

        for idx in range(max_iters):
            try:
                pred = self._call_with_potential_trajectory_truncation(
                    self.react, trajectory, **input_args
                )
            except ValueError as err:
                logger.warning(
                    f"Ending trajectory: agent failed to select valid tool: {err}"
                )
                if recorder:
                    recorder.emit_event(
                        "reasoning",
                        stage_name="thought",
                        status="warning",
                        message=f"Agent failed to select valid tool at iteration {idx}",
                        payload={"iteration": idx, "error": str(err)},
                    )
                break

            thought = pred.next_thought
            tool_name = pred.next_tool_name
            tool_args = pred.next_tool_args

            trajectory[f"thought_{idx}"] = thought
            trajectory[f"tool_name_{idx}"] = tool_name
            trajectory[f"tool_args_{idx}"] = tool_args

            # Emit Thought event
            if recorder:
                recorder.emit_event(
                    "reasoning",
                    stage_name="thought",
                    status="info",
                    message=thought[:500] if thought else "",
                    payload={
                        "iteration": idx,
                        "thought": thought,
                        "planned_tool": tool_name,
                    },
                )

            # Emit Action event
            if recorder:
                safe_args = self._safe_tool_args(tool_args)
                recorder.emit_event(
                    "reasoning",
                    stage_name="action",
                    status="running",
                    message=f"Calling {tool_name}",
                    payload={
                        "iteration": idx,
                        "tool_name": tool_name,
                        "tool_args": safe_args,
                    },
                )

            # Execute tool
            try:
                observation = self.tools[tool_name](**tool_args)
            except Exception as err:
                observation = f"Execution error in {tool_name}: {err}"
                if recorder:
                    recorder.emit_event(
                        "reasoning",
                        stage_name="observation",
                        status="error",
                        message=f"Tool error: {tool_name}",
                        payload={
                            "iteration": idx,
                            "tool_name": tool_name,
                            "error": str(err),
                        },
                    )

            trajectory[f"observation_{idx}"] = observation

            # Emit Observation event
            if recorder and not (
                isinstance(observation, str)
                and observation.startswith("Execution error")
            ):
                obs_preview = (
                    observation[:2000]
                    if isinstance(observation, str)
                    else str(observation)[:2000]
                )
                recorder.emit_event(
                    "reasoning",
                    stage_name="observation",
                    status="ok",
                    message=obs_preview[:500] if obs_preview else "",
                    payload={
                        "iteration": idx,
                        "tool_name": tool_name,
                        "observation_preview": obs_preview,
                        "observation_length": len(observation)
                        if isinstance(observation, str)
                        else 0,
                    },
                )

            if tool_name == "finish":
                if recorder:
                    recorder.emit_event(
                        "reasoning",
                        stage_name="finish",
                        status="ok",
                        message="Agent decided to finish",
                        payload={"iteration": idx, "total_iterations": idx + 1},
                    )
                break

        # Extract final outputs
        try:
            extract = self._call_with_potential_trajectory_truncation(
                self.extract, trajectory, **input_args
            )
        except Exception:
            extract = None

        return trajectory, extract

    def forward(self, **input_args: Any) -> dspy.Prediction:
        recorder = input_args.pop("viewer_recorder", None)
        self._viewer_recorder = recorder

        max_iters = input_args.pop("max_iters", self.max_iters)
        trajectory, extract = self._run_react_loop(input_args, max_iters)

        if extract is not None:
            return dspy.Prediction(trajectory=trajectory, **extract)

        output_fields = ensure_signature(self.signature).output_fields
        fallback = {k: "" for k in output_fields}
        return dspy.Prediction(trajectory=trajectory, **fallback)

    @staticmethod
    def _safe_tool_args(args: dict[str, Any] | Any) -> dict[str, Any]:
        """Truncate large tool args for safe viewer storage."""
        if not isinstance(args, dict):
            return {"raw": str(args)[:500]}
        safe: dict[str, Any] = {}
        for key, value in args.items():
            if isinstance(value, str) and len(value) > 1000:
                safe[key] = value[:1000] + f"... ({len(value)} chars total)"
            else:
                safe[key] = value
        return safe
