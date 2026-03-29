#!/usr/bin/env python3
from genesis.core import EvolutionRunner, EvolutionConfig
from genesis.database import DatabaseConfig
from genesis.launch import LocalJobConfig

job_config = LocalJobConfig(eval_program_path="evaluate.py")

parent_config = dict(
    parent_selection_strategy="weighted",
    parent_selection_lambda=10.0,
)

search_task_sys_msg = """You are an expert machine learning engineer tasked with designing a new agentic system capable of solving complicated math problems coming from the AIME competition.

You will be given a program that implements an agent scaffold called `Agent`. Per problem processed in the `forward` function, the agent has a maximum number of 10 LLM queries. Your goal is to improve the agentic system by suggesting changes to the scaffold.

Some potential directions to explore include:
1. Chain-of-thought prompting
2. Multi-step reasoning and reflection
3. Temperature sampling and ensembling of answers (e.g. 0.0, 0.5, 1.0)
4. Few-shot example construction
5. Different expert prompts (e.g. "You are a skilled mathematician.")
6. Tree search methods (e.g. beam search, tree of thoughts)
7. Self-verification (e.g. different verifiers scoring solutions)

It is well known that reasoning models perform especially well on math problems like AIME. Explore different approaches to elicit deep thinking in simple LLM models.

You will be given a set of performance metrics for the program. Your goal is to maximize the `combined_score` of the program. It resembles the average accuracy of the agent scaffold on the full AIME problem set. Additionally, you will be given the `format_error_count` metric, which is the number of format errors on the 30 problems. You will also be given the `cost` metric, which is the cost of the API calls for the program.

You will have multiple generations to explore different approaches.

It is crucial that the solution format of AIME is preserved. The solution should be a three-digit number (0-999) with no punctuation.
Be creative and think outside the box."""


db_config = DatabaseConfig(
    db_path="evolution_db.sqlite",
    num_islands=4,
    archive_size=40,
    # Inspiration parameters
    elite_selection_ratio=0.3,
    num_archive_inspirations=4,
    num_top_k_inspirations=2,
    # Island migration parameters
    migration_interval=10,
    migration_rate=0.1,  # chance to migrate program to random island
    island_elitism=True,  # Island elite is protected from migration
    enforce_island_separation=True,
    **parent_config,
)


evo_config = EvolutionConfig(
    task_sys_msg=search_task_sys_msg,
    patch_types=["diff", "full", "cross"],
    patch_type_probs=[0.6, 0.3, 0.1],
    num_generations=75,
    max_parallel_jobs=1,
    max_patch_resamples=3,
    max_patch_attempts=3,
    job_type="local",
    language="python",
    llm_models=[
        "gemini-2.5-pro",
        "bedrock/us.anthropic.claude-sonnet-4-20250514-v1:0",
        "azure-o4-mini",
    ],
    llm_kwargs=dict(temperatures=[0.0, 0.5, 1.0], max_tokens=16384),
    meta_rec_interval=10,
    meta_llm_models=["azure-gpt-4.1"],
    meta_llm_kwargs=dict(temperatures=[0.0]),
    embedding_model="text-embedding-3-small",
    init_program_path="initial.py",
    max_novelty_attempts=3,
    code_embed_sim_threshold=0.95,
    novelty_llm_models=["azure-gpt-4.1"],
    novelty_llm_kwargs=dict(temperatures=[0.0]),
    use_text_feedback=True,
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
    results_data = main()
