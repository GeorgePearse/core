#!/usr/bin/env python3
import argparse
from genesis.core import EvolutionRunner, EvolutionConfig
from genesis.database import DatabaseConfig
from genesis.launch import LocalJobConfig
import ale_bench

# Standings: https://atcoder.jp/contests/ahc046/standings

# Full = 40 tasks
# ahc001, ahc002, ahc003, ahc004, ahc005, ahc006, ahc007, ahc008, ahc009, ahc010, ahc011, ahc012, ahc014, ahc015, ahc016, ahc017, ahc019, ahc020, ahc021, ahc024, ahc025, ahc026, ahc027, ahc028, ahc030, ahc031, ahc032, ahc033, ahc034, ahc035, ahc038, ahc039, ahc040, ahc041, ahc042, ahc044, ahc045, ahc046, future-contest-2022-qual, toyota2023summer-final

# Light = 10 tasks
# ahc008, ahc011, ahc015, ahc016, ahc024, ahc025, ahc026, ahc027, ahc039, ahc046


def main(problem_id: str):
    session = ale_bench.start(
        problem_id=problem_id,
        num_workers=13,
    )

    problem = session.problem
    problem_statement_md = problem.statement  # MD-format problem statement

    # Clean statement - delete line and below
    # Remove line and everything that follows with "Tools (Input generator, local tester and visualizer)"
    lines = problem_statement_md.split("\n")
    cleaned_lines = []
    for line in lines:
        if "Tools (Input" in line:
            break
        cleaned_lines.append(line)
    problem_statement_md = "\n".join(cleaned_lines)

    problem_constraints_obj = problem.constraints  # Structured constraints
    session.close()

    ale_bench_task_sys_msg = f"""You are a world-class algorithm engineer, and you are very good at programming. Now, you are participating in a programming contest. You are asked to solve a heuristic problem, known as an NP-hard problem. Here is the problem statement:

{problem_statement_md}

## Problem Constraints

{problem_constraints_obj}

Your goal is to improve the performance of the program by suggesting improvements.

You will be given a set of performance metrics for the program.
Your goal is to maximize the `combined_score` of the program.
Try diverse approaches to solve the problem. Think outside the box."""

    print(ale_bench_task_sys_msg)
    job_config = LocalJobConfig(
        eval_program_path="evaluate.py",
        extra_cmd_args=dict(problem_id=problem_id),
    )

    config = dict(
        parent_selection_strategy="weighted",
        parent_selection_lambda=10.0,
    )

    db_config = DatabaseConfig(
        db_path="evolution_db.sqlite",
        num_islands=2,
        archive_size=50,
        # Inspiration parameters
        elite_selection_ratio=0.3,
        num_archive_inspirations=2,
        num_top_k_inspirations=2,
        # Island migration parameters
        migration_interval=10,
        migration_rate=0.1,  # chance to migrate program to random island
        island_elitism=True,  # Island elite is protected from migration
        enforce_island_separation=True,
        **config,
    )
    print("Initializing with ALE Agent best solution")
    num_generations = 50
    meta_rec_interval = 5
    init_program_path = f"ale_best/{problem_id}.cpp"
    results_dir = f"results_weighted_ale_best/{problem_id}"

    evo_config = EvolutionConfig(
        task_sys_msg=ale_bench_task_sys_msg,
        patch_types=["diff", "full", "cross"],
        patch_type_probs=[0.6, 0.3, 0.1],
        num_generations=num_generations,
        max_parallel_jobs=1,
        max_patch_resamples=3,
        max_patch_attempts=3,
        job_type="local",
        language="cpp",
        llm_models=[
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
            "o4-mini",
            "gpt-5-mini",
            "gpt-5",
        ],
        llm_kwargs=dict(
            temperatures=[0.0, 0.5, 1.0],
            max_tokens=32768,
        ),
        meta_rec_interval=meta_rec_interval,
        meta_llm_models=["gpt-5-mini"],
        meta_llm_kwargs=dict(
            temperatures=[0.0],
            max_tokens=32768,
        ),
        init_program_path=init_program_path,
        results_dir=results_dir,
        max_novelty_attempts=3,
        use_text_feedback=False,
        llm_dynamic_selection="ucb1",
        llm_dynamic_selection_kwargs=dict(exploration_coef=1.0),
    )
    evo_runner = EvolutionRunner(
        evo_config=evo_config,
        job_config=job_config,
        db_config=db_config,
        verbose=True,
    )
    evo_runner.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--problem_id", type=str, default="ahc046")
    args = parser.parse_args()
    problem_id = args.problem_id

    results_data = main(problem_id)
