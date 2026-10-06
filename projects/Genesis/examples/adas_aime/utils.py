# Adapted from https://github.com/SamuelSchmidgall/AgentLaboratory/blob/main/utils.py
import os
import re
import backoff
import re
from pathlib import Path
import openai
from dotenv import load_dotenv


env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

M = 1_000_000

ANSWER_REGEX = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")


def extract_numeric_answer(text: str) -> str:
    """Pulls the last number found in the model's reply."""
    matches = ANSWER_REGEX.findall(text.replace(",", ""))
    return matches[-1].lstrip("0") if matches else text.strip()


def backoff_handler(details):
    exc = details.get("exception")
    if exc:
        print(
            f"OpenAI - Retry {details['tries']} due to error: {exc}. "
            f"Waiting {details['wait']:0.1f}s..."
        )


costs_per_token = {
    "gpt-4.1-nano": {"input": 0.1 / M, "output": 0.4 / M},
    "gpt-4.1-mini": {"input": 0.4 / M, "output": 1.6 / M},
    "gpt-4.1": {"input": 2.0 / M, "output": 8.0 / M},
    "gpt-4o-mini": {"input": 0.15 / M, "output": 0.6 / M},
    "o4-mini": {"input": 1.1 / M, "output": 4.4 / M},
}


class MaxCallsExceededError(Exception):
    """Raised when the maximum number of LLM calls is exceeded."""

    pass


def create_call_limited_query_llm(base_query_llm, max_calls=3):
    """
    Creates a wrapper around query_llm that limits the number of calls
    per forward pass.

    Args:
        base_query_llm: The original query_llm function
        max_calls: Maximum number of calls allowed (default: 3)

    Returns:
        A wrapped query_llm function with call limiting
    """
    import threading

    thread_local = threading.local()

    def limited_query_llm(*args, **kwargs):
        # Initialize call_count for this thread if it doesn't exist
        if not hasattr(thread_local, "call_count"):
            thread_local.call_count = 0

        if thread_local.call_count >= max_calls:
            raise MaxCallsExceededError(
                f"Maximum number of LLM calls ({max_calls}) exceeded"
            )
        thread_local.call_count += 1
        return base_query_llm(*args, **kwargs)

    def reset_calls():
        thread_local.call_count = 0

    def get_call_count():
        return getattr(thread_local, "call_count", 0)

    # Attach reset method to the function
    limited_query_llm.reset_calls = reset_calls
    limited_query_llm.get_call_count = get_call_count

    return limited_query_llm


@backoff.on_exception(
    backoff.expo,
    (
        openai.APIConnectionError,
        openai.APIStatusError,
        openai.RateLimitError,
        openai.APITimeoutError,
    ),
    max_tries=20,
    max_value=20,
    on_backoff=backoff_handler,
)
def query_llm(prompt, system, temperature=0.0, model_name="gpt-4.1-nano"):
    # client = openai.AzureOpenAI(
    #     api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    #     api_version=os.getenv("AZURE_API_VERSION"),
    #     azure_endpoint=os.getenv("AZURE_API_ENDPOINT"),
    # )
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if system is not None:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = [{"role": "user", "content": prompt}]

    if model_name == "o4-mini":
        temperature = 1.0

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        # max_tokens=16384,
    )
    out_text = response.choices[0].message.content
    cost = (
        response.usage.prompt_tokens * costs_per_token[model_name]["input"]
        + response.usage.completion_tokens * costs_per_token[model_name]["output"]
    )
    return out_text, cost


# string normalization from:
# https://github.com/EleutherAI/lm-evaluation-harness/blob/master/lm_eval/tasks/hendrycks_math.py
def is_equiv(str1, str2, verbose=False):
    if str1 is None and str2 is None:
        print("WARNING: Both None")
        return True
    if str1 is None or str2 is None:
        return False

    try:
        ss1 = strip_string(str1)
        ss2 = strip_string(str2)
        if verbose:
            print(ss1, ss2)
        return ss1 == ss2
    except Exception:
        return str1 == str2


def clean_answer(s):
    # makes no difference but can lead to errors
    s = s.replace("\\dfrac", "\\frac")
    s = s.replace("x \\in", "")

    # Remove all \mathbf{...} and replace with just the contents
    s = re.sub(r"\\mathbf\s*{([^}]*)}", r"\1", s)
    s = re.sub(r"\\textbf\s*{([^}]*)}", r"\1", s)
    return s


def remove_boxed(s):
    if "\\boxed " in s:
        left = "\\boxed "
        assert s[: len(left)] == left
        return s[len(left) :]

    left = "\\boxed{"
    if not s.startswith(left):
        return None

    assert s[-1] == "}"

    return clean_answer(s[len(left) : -1])


def last_boxed_only_string(string: str) -> str:
    """
    Extracts the last LaTeX \\boxed{...} or \\fbox{...} command from a string.
    Handles nested braces. If no \\boxed is found, returns an empty string.
    """
    idx = string.rfind("\\boxed")
    if idx < 0:
        idx = string.rfind("\\fbox")
    if idx < 0:
        return ""

    # Find the opening brace
    brace_idx = string.find("{", idx)
    if brace_idx < 0:
        return ""  # No braces, return empty for robustness.

    # Brace matching
    level = 0
    for i in range(brace_idx, len(string)):
        if string[i] == "{":
            level += 1
        elif string[i] == "}":
            level -= 1
            if level == 0:
                return string[idx : i + 1]

    return ""  # Mismatched braces


def fix_fracs(string):
    substrs = string.split("\\frac")
    new_str = substrs[0]
    if len(substrs) > 1:
        substrs = substrs[1:]
        for substr in substrs:
            new_str += "\\frac"
            if substr[0] == "{":
                new_str += substr
            else:
                try:
                    assert len(substr) >= 2
                except AssertionError:
                    return string
                a = substr[0]
                b = substr[1]
                if b != "{":
                    if len(substr) > 2:
                        post_substr = substr[2:]
                        new_str += "{" + a + "}{" + b + "}" + post_substr
                    else:
                        new_str += "{" + a + "}{" + b + "}"
                else:
                    if len(substr) > 2:
                        post_substr = substr[2:]
                        new_str += "{" + a + "}" + b + post_substr
                    else:
                        new_str += "{" + a + "}" + b
    string = new_str
    return string


def fix_a_slash_b(string):
    if len(string.split("/")) != 2:
        return string
    a = string.split("/")[0]
    b = string.split("/")[1]
    try:
        a = int(a)
        b = int(b)
        assert string == "{}/{}".format(a, b)
        new_string = "\\frac{" + str(a) + "}{" + str(b) + "}"
        return new_string
    except AssertionError:
        return string


def remove_right_units(string):
    # "\\text{ " only ever occurs (at least in the val set) when describing
    # units
    if "\\text{ " in string:
        splits = string.split("\\text{ ")
        assert len(splits) == 2
        return splits[0]
    else:
        return string


def fix_sqrt(string):
    if "\\sqrt" not in string:
        return string
    splits = string.split("\\sqrt")
    new_string = splits[0]
    for split in splits[1:]:
        if split[0] != "{":
            a = split[0]
            new_substr = "\\sqrt{" + a + "}" + split[1:]
        else:
            new_substr = "\\sqrt" + split
        new_string += new_substr
    return new_string


def strip_string(string):
    # linebreaks
    string = string.replace("\n", "")

    # remove inverse spaces
    string = string.replace("\\!", "")

    # replace \\ with \
    string = string.replace("\\\\", "\\")

    # replace tfrac and dfrac with frac
    string = string.replace("tfrac", "frac")
    string = string.replace("dfrac", "frac")

    # remove \left and \right
    string = string.replace("\\left", "")
    string = string.replace("\\right", "")

    # Remove circ (degrees)
    string = string.replace("^{\\circ}", "")
    string = string.replace("^\\circ", "")

    # remove dollar signs
    string = string.replace("\\$", "")

    # remove units (on the right)
    string = remove_right_units(string)

    # remove percentage
    string = string.replace("\\%", "")
    string = string.replace("\%", "")  # noqa: W605

    # " 0." equivalent to " ." and "{0." equivalent to "{."
    # Alternatively, add "0" if "." is the start of the string
    string = string.replace(" .", " 0.")
    string = string.replace("{.", "{0.")
    # if empty, return empty string
    if len(string) == 0:
        return string
    if string[0] == ".":
        string = "0" + string

    # to consider: get rid of e.g. "k = " or "q = " at beginning
    if len(string.split("=")) == 2:
        if len(string.split("=")[0]) <= 2:
            string = string.split("=")[1]

    # fix sqrt3 --> sqrt{3}
    string = fix_sqrt(string)

    # remove spaces
    string = string.replace(" ", "")

    # \frac1b or \frac12 --> \frac{1}{b} and \frac{1}{2}, etc.
    # Even works with \frac1{72} (but not \frac{72}1).
    # Also does a/b --> \\frac{a}{b}
    string = fix_fracs(string)

    # manually change 0.5 --> \frac{1}{2}
    if string == "0.5":
        string = "\\frac{1}{2}"
    if string == "5.5":
        string = "\\frac{11}{2}"
    if "(x - 3)(x + 3)" in string:
        string = string.replace("(x - 3)(x + 3)", "(x+3)(x-3)")

    # NOTE: X/Y changed to \frac{X}{Y} in dataset, but in simple cases
    # fix in case the model output is X/Y
    string = fix_a_slash_b(string)

    return string
