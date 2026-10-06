import time
import multiprocessing
import concurrent.futures
from typing import Callable
import pandas as pd
from utils import remove_boxed, last_boxed_only_string, is_equiv


def agent_evaluation(
    Agent,
    query_llm: Callable,
    year: int = 2024,
) -> tuple[float, float, int, int, pd.DataFrame]:
    math_test_set = pd.read_csv("AIME_Dataset_1983_2025.csv")
    math_test_set = math_test_set[math_test_set["Year"] == year]
    agent = Agent(query_llm)

    results = []
    max_workers = min(30, multiprocessing.cpu_count())
    print(f"Loaded AIME dataset with {len(math_test_set)} examples")
    print(f"Running parallel evaluation with {max_workers} workers")
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(process_example, i, example, agent, query_llm): i
            for i, (_, example) in enumerate(math_test_set.iterrows())
        }
        total, correct_count, total_llm_calls, cost_total = 0, 0, 0, 0
        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            total += 1
            try:
                (
                    _idx,
                    problem,
                    response,
                    llm_answer,
                    true_answer,
                    correct,
                    cost,
                    num_llm_calls,
                ) = future.result()
                results.append(
                    {
                        "id": idx,
                        "problem": problem,
                        "response": response,
                        "llm_answer": llm_answer,
                        "true_answer": true_answer,
                        "correct": correct,
                        "cost": cost,
                        "num_llm_calls": num_llm_calls,
                    }
                )
            except Exception as e:
                print(f"Error processing example {idx}: {e}")
                continue

            cost_total += cost
            if correct:
                correct_count += 1
            total_llm_calls += num_llm_calls
            accuracy = (correct_count / total) * 100
            log_message = (
                f"Step: {total}, LLM answer: {llm_answer}, "
                f"True answer: {true_answer}, "
                f"Accuracy: {accuracy:.2f}%, "
                f"Cost: {cost_total:.4f}, "
                f"LLM calls: {total_llm_calls}, "
                f"Avg LLM calls: {total_llm_calls / total}"
            )
            print(log_message)

    if total > 0:
        final_accuracy = (correct_count / total) * 100
        if final_accuracy == 0:
            raise ValueError("Final accuracy is 0. This should not happen.")
        print(
            f"Complete, final accuracy: {final_accuracy:.2f}%, Cost: {cost_total:.2f}"
        )
        print(f"Time taken: {time.time() - start_time:.2f} seconds")
        time_per_example = (time.time() - start_time) / total
        print(f"Time per example: {time_per_example:.2f} seconds")

        df = pd.DataFrame(results)
    else:
        raise ValueError("No examples were processed.")
    return final_accuracy, cost_total, total, total_llm_calls, df


def evaluate_math_correctness(response: str, solution: str) -> tuple[str, str, bool]:
    """Evaluates the correctness of the LLM's response for MATH-500."""
    # true_answer_str = remove_boxed(last_boxed_only_string(solution))
    true_answer_str = solution.strip()
    llm_answer_str = remove_boxed(last_boxed_only_string(response))
    if llm_answer_str is not None:
        llm_answer_str = llm_answer_str.lstrip("0")
        if llm_answer_str == "":
            llm_answer_str = "0"
    true_answer_str = str(solution)

    true_answer = "" if true_answer_str is None else true_answer_str
    llm_answer = "" if llm_answer_str is None else llm_answer_str

    correct = is_equiv(llm_answer, true_answer)
    return llm_answer, true_answer, correct


def evaluate_aime_correctness(
    response: str, solution: str
) -> tuple[str, str, bool, bool]:
    """Evaluates the correctness of the LLM's response for AIME."""
    llm_answer_str = remove_boxed(last_boxed_only_string(response))
    if llm_answer_str is not None:
        llm_answer_str = llm_answer_str.lstrip("0")
        if llm_answer_str == "":
            llm_answer_str = "0"
    true_answer_str = str(solution)

    true_answer = "" if true_answer_str is None else true_answer_str
    llm_answer = "" if llm_answer_str is None else llm_answer_str

    correct = is_equiv(llm_answer, true_answer)
    out_error = len(llm_answer) != 3
    return llm_answer, true_answer, correct, out_error


def process_example(idx, example, agent, query_llm):
    # Reset call count for each example if using call-limited query_llm
    if hasattr(query_llm, "reset_calls"):
        query_llm.reset_calls()

    problem = example["problem"].strip()
    solution = example["answer"]
    response, cost = agent.forward(problem)
    llm_answer, true_answer, correct = evaluate_math_correctness(response, solution)
    num_llm_calls = query_llm.get_call_count()
    return (
        idx,
        problem,
        response,
        llm_answer,
        true_answer,
        correct,
        cost,
        num_llm_calls,
    )
