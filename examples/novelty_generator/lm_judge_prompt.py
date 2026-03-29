import re
from typing import Callable, Tuple


LM_JUDGE_SYSTEM_PROMPT_FMT = """Your role as an assistant is to evaluate a function called "def generate_novelty(rng: int)" whose purpose is to generate a set of diverse pieces of meaningful, inspiring, and novel art from different rng indices. You will be given {number_of_samples} sample outputs to conduct your evaluation of the function. Please evaluate how much the function is able to produce outputs that are truly novel and that can be seen as meaningful and inspiring pieces of art by giving a numeric score that goes from 0 to 1. You should give a high score to functions that are able to produce completely different outputs that resonate with you in different ways through their artistic qualities. However, you should give very low scores and be very critical of functions whose outputs you find meaningless, lacking novelty, or uninspiring. Functions whose scores are higher than 0.5 should only be ones that really produce novel meaningful "art" such that you would be curious to see what they would produce next given a different input, which must not display repetitions or any meaningless results."""


LM_JUDGE_MESSAGE_FMT = """Now it's your turn. Here are the outputs of the function to evaluate:



[BEGIN OF SAMPLE OUTPUTS FROM THE FUNCTION TO EVALUATE]


{sample_function_outputs}


[END OF SAMPLE OUTPUTS FROM THE FUNCTION TO EVALUATE]


Please, make sure you evaluate the above function based on these three criteria, and assign each a value between 0 and 1:

1. Diversity (0–1):
   Assess how novel and unique its outputs are compared to the other generated outputs in the set, assigning lower scores to functions that contain many repetitions.

2. Meaningfulness (0–1):
   Evaluate how meaningful the function outputs are, assigning lower scores to functions that lack structure, meaning, or a clear purpose.

3. Inspirational Quality (0–1):
   Determine how inspiring the outputs of the function are, assigning lower scores to functions whose outputs are predictable, uninspiring, and boring.


Compute your **final novelty evaluation score** as the product of these three criteria:

```
Final Novelty Score = Diversity × Meaningfulness × Inspirational Quality
```

Only functions excelling across all three dimensions should achieve high final novelty scores. Please, ensure your response is very short and avoids detailing how you assessed each output individually. Additionally, ensure you provide your evaluation for these criteria together with the final novelty scores for the function as floats value displayed the the very end using the following format:


diversity = [place diversity floating point score]
meaningfulness = [place weaningfulness floating point score]
inspiration = [inspirational quality score]

novelty_score = [final novelty score, i.e., the product of the above 3]"""


def make_lm_input_and_output_processors(
    number_of_samples: int,
) -> Tuple[Callable, Callable]:
    lm_system_prompt = LM_JUDGE_SYSTEM_PROMPT_FMT.format(
        number_of_samples=number_of_samples,
    )

    def get_evaluation_prompt(
        sample_function_outputs_list: list[str],
    ) -> str:
        sample_function_outputs = ""
        for i, sample_output in enumerate(sample_function_outputs_list):
            sample_function_outputs += f"Sample output {i + 1}:\n{sample_output}\n\n"
        sample_function_outputs = sample_function_outputs[:-1]

        lm_message = LM_JUDGE_MESSAGE_FMT.format(
            sample_function_outputs=sample_function_outputs,
        )

        return lm_system_prompt, lm_message

    def extract_results(text: str) -> dict[str, float]:
        # regexes for each target score in the lm judge question fmt
        pats = {
            "diversity_score": r"diversity\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
            "meaningfulness_score": r"(?:meaningfulness|weaningfulness)\s*[:=]\s*"
            + r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
            "inspiration_score": r"inspiration\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
            "final_novelty_score": r"novelty[\s_-]?score\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",
        }

        scores: dict[str, float] = {}

        # keep only the last match
        for key, pat in pats.items():
            last = None
            for m in re.finditer(pat, text, flags=re.I):
                last = m
            if last:
                scores[key] = float(last.group(1))
        return scores

    return get_evaluation_prompt, extract_results


def test_get_evaluation_prompt():
    number_of_samples = 3
    sample_outputs = [
        "Sample output 1: Artistic piece 1",
        "Sample output 2: Artistic piece 2",
        "Sample output 3: Artistic piece 3",
    ]

    prompt = get_evaluation_prompt(
        number_of_samples=number_of_samples,
        sample_function_outputs_list=sample_outputs,
        use_evaluation_examples=True,
    )

    print(prompt)


def test_extract_results():
    text = """
    diversity = 0.8000.
    meaningfulness =   0.7
    inspiration = 0.9

    novelty_score = 0.504
    """

    results = extract_results(text)
    print(results)


if __name__ == "__main__":
    get_evaluation_prompt, extract_results = make_lm_input_and_output_processors(
        number_of_samples=3,
    )

    test_get_evaluation_prompt()
    test_extract_results()
