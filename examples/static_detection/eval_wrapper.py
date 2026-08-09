#!/usr/bin/env python3
"""Eval wrapper for Rust genesis runner. Reads code from GENESIS_CODE_PATH,
strips markdown fences, evaluates, and prints JSON to stdout."""
import importlib.util
import json
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))


def strip_markdown_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def main():
    code_path = os.environ.get("GENESIS_CODE_PATH")
    if not code_path:
        print(json.dumps({"correct": False, "combined_score": 0.0,
                          "text_feedback": "GENESIS_CODE_PATH not set"}))
        return

    with open(code_path, "r") as f:
        raw = f.read()

    code = strip_markdown_fences(raw)

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
    tmp.write(code)
    tmp.close()

    spec = importlib.util.spec_from_file_location("candidate", tmp.name)
    candidate = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(candidate)
    except Exception as e:
        os.unlink(tmp.name)
        print(json.dumps({"correct": False, "combined_score": 0.0,
                          "text_feedback": f"Import error: {e}"}))
        return

    if not hasattr(candidate, "run_experiment"):
        os.unlink(tmp.name)
        print(json.dumps({"correct": False, "combined_score": 0.0,
                          "text_feedback": "Missing run_experiment function"}))
        return

    from evaluate import _generate_pairs, aggregate_metrics, validate_fn

    try:
        static_pairs, moving_pairs = _generate_pairs()
        result = candidate.run_experiment(
            static_pairs=static_pairs, moving_pairs=moving_pairs
        )

        ok, err = validate_fn(result)
        if not ok:
            print(json.dumps({"correct": False, "combined_score": 0.0,
                              "text_feedback": f"Validation failed: {err}"}))
            return

        metrics = aggregate_metrics([result])
        print(json.dumps({
            "correct": True,
            "combined_score": metrics["combined_score"],
            "text_feedback": (
                f"AUC={metrics['public']['auc']}, "
                f"separation={metrics['public']['separation']}x, "
                f"speed={metrics['public']['avg_time_ms']}ms"
            ),
        }))
    except Exception:
        print(json.dumps({"correct": False, "combined_score": 0.0,
                          "text_feedback": f"Eval error: {traceback.format_exc()[:500]}"}))
    finally:
        os.unlink(tmp.name)


if __name__ == "__main__":
    main()
