# Rank: 2
# Generation: 10
# Score: 34.444444
# Name: expert_ensemble_with_self_correction
# ID: 322868de-8d9b-4cfa-8506-da037531d38c
# Parent ID: c39d7f98-e09e-47c4-9829-1aae27e66337
# Type: full
# Description: The previous agent, while using an ensemble approach, suffered from correlated errors where all initial solutions made the same mistake, and the single critic failed to identify it. This new design tackles that issue head-on with a more robust, multi-stage reasoning process within the 10-call limit.

# 1.  **Diverse Expert Personas:** Instead of generating three similar solutions, the agent now prompts the LLM with three distinct "expert personas": a methodical mathematician, an intuitive pattern-seeker, and an algorithmic thinker. This increases the diversity of initial approaches, making it less likely that all three will share the same fundamental flaw.

# 2.  **Independent Peer Review & Self-Correction:** The single "critic" stage is replaced by a more rigorous, parallelized "peer review" stage. Each of the three expert solutions is independently reviewed by a skeptical LLM agent. The prompt for this reviewer explicitly instructs it to be highly critical and, crucially, to verify any discovered patterns on new, unseen examples. This directly targets the failure mode observed in the game theory problem where a pattern was incorrectly generalized. This stage produces three corrected solution attempts.

# 3.  **Informed Synthesis:** A final "Editor-in-Chief" agent synthesizes the final answer. It receives all three original solutions *and* their corresponding critiques. This richer context allows it to make a much more informed judgment, identify the most sound line of reasoning, and construct a final answer that learns from the mistakes of the initial attempts.

# This new architecture uses more of the available LLM calls (7 calls: 3 for generation, 3 for review, 1 for synthesis) to create a more robust system that diversifies its initial thinking and then rigorously verifies it before reaching a conclusion.

"""Agent design evaluation on math tasks."""

import re
from typing import Callable, List, Optional, Tuple, Dict
from collections import Counter, defaultdict
from math_eval import agent_evaluation


# EVOLVE-BLOCK-START
import re
from collections import Counter


class Agent:
    def __init__(
        self,
        query_llm: Callable,
        temperature=0.0,
    ):
        self.query_llm = query_llm
        self.output_format_instructions = "On the final line output only the digits of the answer (0-999). Provide your final answer enclosed in a LaTeX \\boxed{{...}} command."

        # Parameters
        self.generation_temperature = 0.7
        self.review_temperature = 0.1
        self.synthesis_temperature = 0.0

        # Use 3 experts to stay within a 10-call limit (3 gen + 3 review + 1 synth = 7 calls)
        self.num_experts = 3
        self.expert_personas = [
            "You are a meticulous and cautious mathematician. Your guiding principle is 'slow and steady wins the race'. You solve problems by breaking them down into the smallest possible steps based on fundamental principles. You avoid leaps of logic and verify each step before proceeding.",
            "You are a brilliant and intuitive mathematician, known for finding elegant, non-obvious solutions. You look for symmetries, invariants, or a change of perspective that radically simplifies the problem. You trust your insights but explain them clearly.",
            "You are a mathematician with a strong background in computer science. You approach problems by trying to frame them algorithmically. You think in terms of states, transitions, and recurrence relations, and you analyze the behavior of these systems to find the solution.",
        ]

    def _extract_answer(self, text: str) -> Optional[str]:
        """Extracts the final answer from a \\boxed{} environment."""
        if not text:
            return None
        matches = re.findall(r"\\boxed\{(\d{1,3})\}", text)
        if matches:
            return matches[-1]
        return None

    def forward(self, problem: str) -> tuple[str, float]:
        """
        Solves a problem using a multi-persona ensemble with peer review and synthesis.
        """
        total_cost = 0.0

        # === STAGE 1: Generate Diverse Solutions with Expert Personas ===
        solutions = []
        for i in range(self.num_experts):
            persona = self.expert_personas[i % len(self.expert_personas)]
            prompt = f"Solve the following AIME problem by thinking step-by-step. {self.output_format_instructions}\n\nPROBLEM:\n{problem}\n\nSOLUTION:"
            try:
                response, cost = self.query_llm(
                    prompt=prompt,
                    system=persona,
                    temperature=self.generation_temperature,
                )
                solutions.append(response)
                total_cost += cost
            except Exception:
                # If a query fails, we proceed with fewer solutions.
                solutions.append(f"Expert {i + 1} failed to generate a solution.")

        # === STAGE 2: Independent Peer Review & Self-Correction ===
        critiques = []
        reviewer_system_prompt = "You are a skeptical peer reviewer examining a proposed solution to an AIME problem. Your task is to be extremely critical. Do not accept any statement at face value. Re-read the original problem carefully. Check calculations. Scrutinize the logical flow. **Pattern Verification:** If the solution relies on a pattern, you MUST test it on several new examples. If you find an error, clearly explain the flaw and provide a corrected line of reasoning and a final corrected answer. If the solution is completely sound, state that and re-state the final answer."
        for sol in solutions:
            prompt = f"Original Problem:\n{problem}\n\nProposed Solution to Review:\n{sol}\n\nYour Critical Review and Corrected Solution:"
            try:
                review, cost = self.query_llm(
                    prompt=prompt,
                    system=reviewer_system_prompt,
                    temperature=self.review_temperature,
                )
                critiques.append(review)
                total_cost += cost
            except Exception:
                critiques.append("Reviewer failed to provide a critique.")

        # === STAGE 3: Synthesize Final Answer ===
        synthesis_prompt_parts = [
            f"You are the Editor-in-Chief of a prestigious mathematics journal, responsible for publishing the final, canonical solution to this AIME problem. You have received {self.num_experts} independent attempts and their corresponding critical reviews. Your task is to produce the definitive solution.\n\nProblem:\n{problem}"
        ]
        for i, (sol, crit) in enumerate(zip(solutions, critiques)):
            synthesis_prompt_parts.append(
                f"\n--- ATTEMPT {i + 1} ---\nSolution: {sol}\nCritique: {crit}\n---"
            )

        synthesis_prompt_parts.append(
            f"\nSYNTHESIS AND FINAL JUDGEMENT:\n1. First, briefly state the final numerical answer proposed by each of the reviewed attempts.\n2. Based on the critiques, determine which approach is the most reliable, or if all are flawed. Explain your reasoning.\n3. Construct the final, clear, step-by-step, correct solution. Leverage insights from the valid parts of the attempts and correct any identified errors. {self.output_format_instructions}"
        )

        synthesizer_prompt = "\n".join(synthesis_prompt_parts)
        synthesizer_system_prompt = "You are a master mathematician and editor, synthesizing multiple reviewed solutions into one canonical, correct answer."

        final_response = ""
        try:
            final_response, cost = self.query_llm(
                prompt=synthesizer_prompt,
                system=synthesizer_system_prompt,
                temperature=self.synthesis_temperature,
            )
            total_cost += cost
        except Exception:
            pass  # Fallback logic will handle this.

        # === Fallback Logic ===
        if self._extract_answer(final_response) is None:
            # First, trust the reviewed answers
            reviewed_answers = [self._extract_answer(c) for c in critiques]
            valid_reviewed_answers = [
                ans for ans in reviewed_answers if ans is not None
            ]

            if valid_reviewed_answers:
                most_common_answer = Counter(valid_reviewed_answers).most_common(1)[0][
                    0
                ]
                final_response += f"\n\n[Fallback to Majority Vote on Reviewed Solutions]\n\\boxed{{{most_common_answer}}}"
            else:
                # If reviews didn't produce answers, check original solutions
                original_answers = [self._extract_answer(s) for s in solutions]
                valid_original_answers = [
                    ans for ans in original_answers if ans is not None
                ]
                if valid_original_answers:
                    most_common_answer = Counter(valid_original_answers).most_common(1)[
                        0
                    ][0]
                    final_response += f"\n\n[Fallback to Majority Vote on Original Solutions]\n\\boxed{{{most_common_answer}}}"
                else:
                    # Ultimate fallback
                    final_response += "\n\n[Fallback] Could not determine a final answer from any stage.\n\\boxed{000}"

        return final_response, total_cost


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
