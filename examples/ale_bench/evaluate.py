import argparse
import json
import os
import traceback
from pathlib import Path

import ale_bench
from ale_bench.result import CaseResult, JudgeResult, Result


def result_feedback(result: Result) -> CaseResult:
    if result.overall_judge_result == JudgeResult.ACCEPTED:
        return result.case_results[0]
    else:
        selected_case_idx = 0
        for idx, case_result in enumerate(result.case_results):
            if case_result.judge_result == result.overall_judge_result:
                selected_case_idx = idx
                break
        return result.case_results[selected_case_idx]


def main(program_path: str, results_dir: str, problem_id: str) -> None:
    """Runs the evaluation using the genesis.eval utility."""
    print(f"Problem ID: {problem_id}")
    print(f"Evaluating program: {program_path}")
    print(f"Saving results to: {results_dir}")

    root_dir = Path(__file__).resolve().parent
    session_file = root_dir / results_dir / "session.json"

    # create results_dir if it doesn't exist
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)

    try:
        session = None
        if not session_file.exists():
            session = ale_bench.start(
                problem_id=problem_id,
                lite_version=True,
                num_workers=13,
            )
        else:
            session = ale_bench.restart(session_saved_file=session_file, num_workers=13)
        if not session:
            raise RuntimeError("Failed to start or restart the session.")

        code = Path(program_path).read_text()
        print("Problem metadata: ", session.problem.metadata)
        maximize = session.problem.metadata.score_type == "maximize"
        print("MAXIMIZE SCORE: ", maximize)
        # DEFAULT LITE EVAL USES ONLY 5 TEST CASES
        # public_result = session.public_eval(code=code, code_language="cpp20")

        # ALE-AGENT: USE SPECIFIED NUMBER OF GENERATED TEST CASES
        num_public_cases = 50
        cases = session.case_gen(list(range(num_public_cases)))
        public_result = session.case_eval(
            cases, code, code_language="cpp20", skip_local_visualization=True
        )
        # Store the public_result as JSON in the results directory
        public_result_json_path = Path(results_dir) / "public_result.json"
        public_json_str = public_result.model_dump_json(indent=4)
        public_result_json_path.write_text(public_json_str)
        public_json = json.loads(public_json_str)
        public_passed_cases, public_failed_cases = 0, 0
        for case in public_json["case_results"]:
            if case["judge_result"] == "ACCEPTED":
                public_passed_cases += 1
            else:
                public_failed_cases += 1
        print(
            f"Passed {public_passed_cases} cases, failed {public_failed_cases} cases out of {num_public_cases}"
        )

        print(
            f"Initial Public Score: {public_result.overall_absolute_score} - Mean Score: {public_result.overall_absolute_score / num_public_cases}"
        )
        extracted_case = result_feedback(public_result)
        session.save(session_file)

        public_metrics = {
            "judge_result": public_result.overall_judge_result.value,
            "max_execution_time_sec": max(
                [
                    case_result.execution_time
                    for case_result in public_result.case_results
                ]
            ),
            "max_memory_usage_mib": max(
                [case_result.memory_usage for case_result in public_result.case_results]
            )
            // 1024
            // 1024,
            "num_passed_cases": public_passed_cases,
            "num_failed_cases": public_failed_cases,
            "standard_error": extracted_case.error_str,
            "message": extracted_case.message,
        }

        if maximize:
            score_to_opt = public_result.overall_absolute_score / num_public_cases
        else:
            score_to_opt = public_result.overall_absolute_score / num_public_cases * -1
        metrics = {
            "combined_score": score_to_opt,
            "public": public_metrics,
        }
        correct = public_metrics["judge_result"] == "ACCEPTED"
        error = ""

        private_result, final_rank, final_performance = session.private_eval(
            code, code_language="cpp20"
        )
        # Store the private_result as JSON in the results directory
        private_result_json_path = Path(results_dir) / "private_result.json"
        private_json_str = private_result.model_dump_json(indent=4)
        private_result_json_path.write_text(private_json_str)
        private_json = json.loads(private_json_str)

        private_passed_cases, private_failed_cases = 0, 0
        num_private_cases = len(private_json["case_results"])
        for case in private_json["case_results"]:
            if case["judge_result"] == "ACCEPTED":
                private_passed_cases += 1
            else:
                private_failed_cases += 1
        print(
            f"Passed {private_passed_cases} cases, failed {private_failed_cases} cases out of {num_private_cases}"
        )

        print(
            f"Final Private Score: {private_result.overall_absolute_score} - Mean Score: {private_result.overall_absolute_score / num_private_cases}"
        )
        print(f"Rank: {final_rank}, Performance: {final_performance}")

        private_metrics = {
            "private_rank": final_rank,
            "private_performance": final_performance,
            "num_private_passed_cases": private_passed_cases,
            "num_private_failed_cases": private_failed_cases,
        }
        metrics["private"] = private_metrics

        # Monitor resource consumption
        print(f"Current Resource Usage: {session.current_resource_usage}")
        print(f"Remaining Resources: {session.remaining_resource_usage}")
    except Exception as e:
        print(f"Evaluation failed completely: {str(e)}")
        print(traceback.format_exc())
        metrics = {
            "combined_score": 0.0,
            "public": {"judge_result": "REJECTED"},
            "private": {
                "private_rank": 0,
                "private_performance": 0,
                "num_private_passed_cases": 0,
                "num_private_failed_cases": 0,
            },
        }
        correct = False
        error = str(e)

    # Save correct to JSON file
    correct_file = os.path.join(results_dir, "correct.json")
    with open(correct_file, "w") as f:
        json.dump({"correct": correct, "error": error}, f, indent=4)
    print(f"Correct saved to {correct_file}")

    # Save metrics to JSON file
    metrics_file = os.path.join(
        results_dir,
        "metrics.json",
    )
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=4)
    print(f"Metrics saved to {metrics_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Agent evaluation script using genesis.eval"
    )
    parser.add_argument(
        "--program_path",
        type=str,
        default="initial.cpp",
        help="Path to the program to evaluate",
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default="results",
        help="Directory to save results and logs (metrics.json, correct.json)",
    )
    parser.add_argument(
        "--problem_id",
        type=str,
        default="ahc046",
        help="Problem ID",
    )
    parsed_args = parser.parse_args()
    main(
        parsed_args.program_path,
        parsed_args.results_dir,
        parsed_args.problem_id,
    )
