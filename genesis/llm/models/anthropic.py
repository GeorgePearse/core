import backoff
import anthropic
from .pricing import CLAUDE_MODELS
from .result import QueryResult
import logging

logger = logging.getLogger(__name__)


MAX_TRIES = 20
MAX_VALUE = 20


def backoff_handler(details):
    exc = details.get("exception")
    if exc:
        logger.info(
            f"Anthropic - Retry {details['tries']} due to error: {exc}. Waiting {details['wait']:0.1f}s..."
        )


@backoff.on_exception(
    backoff.expo,
    (
        anthropic.APIConnectionError,
        anthropic.APIStatusError,
        anthropic.RateLimitError,
        anthropic.APITimeoutError,
    ),
    max_tries=MAX_TRIES,
    max_value=MAX_VALUE,
    on_backoff=backoff_handler,
)
def query_anthropic(
    client,
    model,
    msg,
    system_msg,
    msg_history,
    output_model,
    model_posteriors=None,
    tools=None,
    **kwargs,
) -> QueryResult:
    """Query Anthropic/Bedrock model."""
    new_msg_history = list(msg_history)
    if msg:
        new_msg_history.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": msg,
                    }
                ],
            }
        )

    if output_model is None:
        call_kwargs = {
            "model": model,
            "system": system_msg,
            "messages": new_msg_history,
            **kwargs,
        }
        if tools:
            call_kwargs["tools"] = tools

        response = client.messages.create(**call_kwargs)

        # Separate thinking from non-thinking content
        thought = ""
        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "thinking":
                thought += block.thinking
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                        "type": "tool_use",
                    }
                )
    else:
        raise NotImplementedError("Structured output not supported for Anthropic.")

    # Only append assistant content if there is text content or tool calls
    if content or tool_calls:
        assistant_msg = {"role": "assistant", "content": []}
        if content:
            assistant_msg["content"].append(
                {
                    "type": "text",
                    "text": content,
                }
            )
        if tool_calls:
            # We need to preserve tool calls in history for the next turn
            # Anthropic expects tool_use blocks in assistant message
            for tc in tool_calls:
                assistant_msg["content"].append(
                    {
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["name"],
                        "input": tc["input"],
                    }
                )
        new_msg_history.append(assistant_msg)

    input_cost = CLAUDE_MODELS[model]["input_price"] * response.usage.input_tokens
    output_cost = CLAUDE_MODELS[model]["output_price"] * response.usage.output_tokens
    result = QueryResult(
        content=content,
        msg=msg,
        system_msg=system_msg,
        new_msg_history=new_msg_history,
        model_name=model,
        kwargs=kwargs,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cost=input_cost + output_cost,
        input_cost=input_cost,
        output_cost=output_cost,
        thought=thought,
        tool_calls=tool_calls,
        model_posteriors=model_posteriors,
    )
    return result
