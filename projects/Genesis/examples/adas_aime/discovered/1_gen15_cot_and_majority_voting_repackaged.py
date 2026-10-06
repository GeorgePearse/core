# Rank: 1
# Generation: 15
# Score: 32.222222
# Name: cot_and_majority_voting_repackaged
# ID: 9b668723-746f-45dc-8c18-7c81b4453726
# Parent ID: 414e0080-9583-4e3a-9b9a-995842831fbf
# Type: diff
# Description: This approach combines two effective techniques to improve mathematical reasoning performance. The previous submission failed due to a technical issue with the diff format, not the method itself. This is a repackaged version of the same idea.

# 1.  **Chain-of-Thought (CoT) Prompting**: The prompt is enhanced to explicitly ask the LLM to "think step by step." The system prompt is also made more descriptive, guiding the model towards producing a detailed, structured reasoning process. This is a well-established method for improving performance on complex reasoning tasks.

# 2.  **Ensemble with Majority Voting**: Instead of relying on a single LLM output, the agent now generates 5 independent solutions. By setting the sampling temperature to 0.7, we encourage diversity in the generated reasoning paths. The agent then extracts the final answer from each solution and uses a majority vote to determine the most reliable result. The final output submitted is one of the original, complete reasoning paths that led to the majority answer. This ensemble technique makes the system more robust to random errors and hallucinations in any single generation, significantly improving accuracy.

# These changes transform the agent from a simple one-shot querier into a more robust, multi-path reasoner that is less susceptible to single-path failures.

"""Agent design evaluation on math tasks."""

import re
from typing import Callable, List, Optional, Tuple, Dict
from collections import Counter, defaultdict
from math_eval import agent_evaluation


# EVOLVE-BLOCK-START
class Agent:
    def __init__(
        self,
        query_llm: Callable,
        temperature=0.7,
    ):
        self.output_format_instructions = "On the final line output only the digits of the answer (0‑999). Provide your final answer enclosed in a LaTeX \\boxed{{...}} command."
        self.query_llm = query_llm
        self.temperature = temperature
        self.num_samples = 5

    def forward(self, problem: str) -> tuple[str, float]:
        """
        Queries the LLM multiple times to generate a diverse set of solutions
        and then uses majority voting to determine the final answer.
        """
        system_prompt, task_prompt = self.get_prompt_for_task(problem)

        responses = []
        answers = []
        total_cost = 0.0

        # We are limited to 10 calls, so let's ensure we don't exceed that.
        # We'll use self.num_samples, which is less than 10.
        for _ in range(self.num_samples):
            response, cost = self.query_llm(
                prompt=task_prompt,
                system=system_prompt,
                temperature=self.temperature,
            )
            total_cost += cost
            responses.append(response)

            match = re.search(r"\\boxed\{(\d+)\}", response)
            if match:
                answers.append(match.group(1))

        if not answers:
            # Fallback to the first response if no answer is found in any sample
            return responses[0] if responses else "", total_cost

        # Find the most common answer
        try:
            majority_answer = Counter(answers).most_common(1)[0][0]
        except IndexError:
            # This can happen if 'answers' is empty.
            return responses[0] if responses else "", total_cost

        # Return the first response that contains the majority answer
        for response in responses:
            if f"\\boxed{{{majority_answer}}}" in response:
                return response, total_cost

        # As a final fallback, return the first valid response we got.
        return responses[0], total_cost

    def get_prompt_for_task(self, problem: str) -> tuple[str, str]:
        system_prompt = "You are a skilled mathematician who is an expert in thinking step-by-step to reach a solution."
        task_prompt = (
            f"Solve the following math problem: {problem}\n\n"
            f"Let's think step by step.\n\n"
            f"{self.output_format_instructions}"
        )
        return system_prompt, task_prompt


# EVOLVE-BLOCK-END


def run_experiment(**kwargs):
    from utils import query_llm, create_call_limited_query_llm
    from functools import partial

    # Create base query_llm function
    base_query_llm = partial(query_llm, model_name=kwargs["model_name"])

    # Wrap it with call limiting (max 10 calls per forward pass)
    limited_query_llm = create_call_limited_query_llm(
        base_query_llm,
        max_calls=kwargs["max_calls"],
    )

    accuracy, cost_total, processed, num_llm_calls, df = agent_evaluation(
        Agent, limited_query_llm, year=kwargs["year"]
    )
    return accuracy, cost_total, processed, num_llm_calls, df
