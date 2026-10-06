#!/usr/bin/env python3
from genesis.core import EvolutionRunner, EvolutionConfig
from genesis.database import DatabaseConfig
from genesis.launch import LocalJobConfig

job_config = LocalJobConfig(eval_program_path="evaluate.py")

# Database configuration
db_config = DatabaseConfig(
    db_path="evolution_db.sqlite",
    num_islands=2,
    archive_size=40,
    elite_selection_ratio=0.3,
    num_archive_inspirations=4,
    num_top_k_inspirations=2,
    migration_interval=10,
    migration_rate=0.1,
    island_elitism=True,
    parent_selection_strategy="weighted",
    parent_selection_lambda=10.0,
)

# Task description
task_sys_msg = """
You are an expert in computer vision and performance optimization.
Your task is to optimize a function `run_conversion(mask)` that converts a binary mask to a list of polygons.

The goal is to maximize the Intersection over Union (IoU) while minimizing execution time.
The current implementation uses OpenCV contours, but there may be faster or more accurate ways, 
or ways to simplify the polygons to improve speed without losing too much accuracy.

Consider:
1. Downsampling the mask before processing.
2. Approximating contours with fewer points.
3. Using different algorithms for contour finding.
4. Optimizing the numpy operations.

The input `mask` is a numpy uint8 array.
The output should be a list of numpy arrays, each shape (N, 2).
"""

# Evolution configuration
evo_config = EvolutionConfig(
    task_sys_msg=task_sys_msg,
    patch_types=["diff", "full", "cross"],
    patch_type_probs=[0.6, 0.3, 0.1],
    num_generations=50,
    max_parallel_jobs=4,
    max_patch_resamples=3,
    max_patch_attempts=3,
    job_type="local",
    language="python",
    llm_models=[
        "gpt-4.1",
        "gpt-4.1-mini",
        "claude-3-5-sonnet-latest",
    ],
    llm_kwargs=dict(
        temperatures=[0.0, 0.5, 1.0],
        max_tokens=4096,
    ),
    meta_rec_interval=10,
    meta_llm_models=["gpt-4.1"],
    meta_llm_kwargs=dict(temperatures=[0.0], max_tokens=2048),
    embedding_model="text-embedding-3-small",
    llm_dynamic_selection="ucb",
    init_program_path="initial.py",
    results_dir="results_mask_seg",
)


def main():
    evo_runner = EvolutionRunner(
        evo_config=evo_config,
        job_config=job_config,
        db_config=db_config,
        verbose=True,
    )
    evo_runner.run()


if __name__ == "__main__":
    main()
