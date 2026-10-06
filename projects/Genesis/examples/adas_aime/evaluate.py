import argparse
from typing import Dict, Any, List, Tuple
import numpy as np
from genesis.core import run_genesis_eval


def construct_text_feedback(all_df) -> str:
    """Collect feedback from all wrong answers."""
    extra_dfs = [df.sort_values("id").reset_index(drop=True) for df in all_df]
    # Find ids where all three dataframes have "correct" == False
    ids_all_incorrect = set.intersection(
        *[set(df.loc[df["correct"] == False, "id"]) for df in extra_dfs]
    )
    ids_all_incorrect = sorted(ids_all_incorrect)
    # Select from first dataframe
    df0_selected = extra_dfs[0][extra_dfs[0]["id"].isin(ids_all_incorrect)]
    random_id = df0_selected.sample(1)["id"].values[0]
    false_answer = df0_selected[df0_selected["id"] == random_id]
    text_feedback = f"# Example of an AIME problem that could not be answered correctly:\n\n {false_answer.iloc[0]['problem']}"
    text_feedback += (
        f"\n\n# The Agent's wrong full response:\n\n{false_answer.iloc[0]['response']}"
    )
    text_feedback += (
        f"\n\n# The Agent's submit answer:\n\n{false_answer.iloc[0]['llm_answer']}"
    )
    text_feedback += f"\n\n#The ground truth problem answer:\n\n{false_answer.iloc[0]['true_answer']}"
    return text_feedback


def default_aggregate_metrics(
    results: List[Tuple[float, float, float, float]],
) -> Dict[str, float]:
    """Default aggregator for results."""
    if not results:
        public_metrics = {
            "performance": 0.0,
            "cost": 0.0,
        }
        private_metrics = {"processed": 0}
        metrics = {
            "public": public_metrics,
            "private": private_metrics,
            "combined_score": 0.0,
            "text_feedback": "",
        }
        return metrics

    (
        all_performance,
        all_cost,
        all_processed,
        all_num_llm_calls,
        all_df,
    ) = zip(*results)
    all_processed = sum(all_processed)
    total_num_llm_calls = sum(all_num_llm_calls)
    public_metrics = {
        "cost": float(np.mean(all_cost)),
        "avg_num_llm_calls": float(total_num_llm_calls / all_processed),
    }
    private_metrics = {
        "all_performance": all_performance,
        "all_cost": all_cost,
        "all_processed": all_processed,
        "all_num_llm_calls": all_num_llm_calls,
    }
    # Store extra data as pickle file
    extra_data = {
        "df": all_df,
    }
    text_feedback = construct_text_feedback(all_df)
    metrics = {
        "public": public_metrics,
        "private": private_metrics,
        "combined_score": float(np.mean(all_performance)),
        "extra_data": extra_data,
        "text_feedback": text_feedback,
    }
    return metrics


def get_experiment_kwargs(
    run_idx: int, model_name: str, year: int, max_calls: int
) -> Dict[str, Any]:
    """Provides keyword arguments for each experiment run."""
    return {"model_name": model_name, "year": year, "max_calls": max_calls}


def main(
    program_path: str,
    results_dir: str,
    model_name: str,
    year: int,
    num_experiment_runs: int = 5,
    max_calls: int = 10,
) -> None:
    """Runs the evaluation using the genesis.eval utility."""
    print(f"Evaluating program: {program_path}")
    print(f"Saving results to: {results_dir}")
    print(f"Using model: {model_name}")
    print(f"Using year: {year}")
    print(f"Using max calls: {max_calls}")
    print(f"Using num experiment runs: {num_experiment_runs}")

    from functools import partial

    get_kwargs_for_run = partial(
        get_experiment_kwargs,
        model_name=model_name,
        year=year,
        max_calls=max_calls,
    )

    metrics, correct, error = run_genesis_eval(
        program_path=program_path,
        results_dir=results_dir,
        experiment_fn_name="run_experiment",
        num_runs=num_experiment_runs,
        get_experiment_kwargs=get_kwargs_for_run,
        aggregate_metrics_fn=default_aggregate_metrics,
    )

    if correct:
        print("Evaluation completed successfully.")
        print("Metrics:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")
    else:
        print(f"Evaluation failed: {error}")
        print("Default metrics stored due to error:")
        for key, value in metrics.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Agent evaluation script using genesis.eval"
    )
    parser.add_argument(
        "--program_path",
        type=str,
        default="initial.py",
        help="Path to the program to evaluate (must contain 'run_experiment')",
    )
    parser.add_argument(
        "--results_dir",
        type=str,
        default="results",
        help="Directory to save results and logs (metrics.json, correct.json)",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="gpt-4.1-nano",
        help="Name of the model to use for evaluation",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2024,
        help="Year of the AIME dataset to use for evaluation",
    )
    parser.add_argument(
        "--num_experiment_runs",
        type=int,
        default=3,
        help="Number of experiment runs to perform",
    )
    parser.add_argument(
        "--max_calls",
        type=int,
        default=10,
        help="Maximum number of calls to the LLM",
    )
    args = parser.parse_args()
    main(
        args.program_path,
        args.results_dir,
        args.model_name,
        args.year,
        args.num_experiment_runs,
        args.max_calls,
    )
