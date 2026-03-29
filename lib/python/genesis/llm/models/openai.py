import backoff
import openai
from .pricing import OPENAI_MODELS, OPENROUTER_MODELS
from .result import QueryResult
import logging

logger = logging.getLogger(__name__)


def backoff_handler(details):
    exc = details.get("exception")
    if exc:
        logger.warning(
            f"OpenAI - Retry {details['tries']} due to error: {exc}. Waiting {details['wait']:0.1f}s..."
        )


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
def query_openai(
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
    """Query OpenAI model."""
    new_msg_history = list(msg_history)
    if msg:
        new_msg_history.append({"role": "user", "content": msg})

    # Build messages list for chat completions API
    messages = [{"role": "system", "content": system_msg}] + new_msg_history

    # Remove unsupported kwargs and rename max_output_tokens to max_tokens for chat completions
    chat_kwargs = {}
    for k, v in kwargs.items():
        if k == "input":
            continue
        elif k == "max_output_tokens":
            chat_kwargs["max_tokens"] = v
        else:
            chat_kwargs[k] = v

    if tools:
        chat_kwargs["tools"] = tools

    tool_calls = []
    thought = ""

    if output_model is None:
        # Try the new responses API first, fall back to chat completions
        try:
            response = client.responses.create(
                model=model,
                input=messages,
                **chat_kwargs,
            )
            try:
                content = response.output[0].content[0].text
            except Exception:
                # Reasoning models - ResponseOutputMessage
                content = response.output[1].content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
        except AttributeError:
            # Fall back to chat completions API for older openai versions
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                **chat_kwargs,
            )
            message = response.choices[0].message
            content = message.content or ""
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                    )

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        assistant_msg = {"role": "assistant"}
        if content:
            assistant_msg["content"] = content
        if tool_calls:
            assistant_msg["tool_calls"] = response.choices[0].message.tool_calls

        new_msg_history.append(assistant_msg)
    else:
        # For structured output, use chat completions with response_format
        try:
            response = client.responses.parse(
                model=model,
                input=messages,
                text_format=output_model,
                **chat_kwargs,
            )
            content = response.output_parsed
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
        except AttributeError:
            # Fall back to chat completions
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                **chat_kwargs,
            )
            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        if isinstance(content, str):
            new_msg_history.append({"role": "assistant", "content": content})
        else:
            new_content = ""
            for i in content:
                new_content += i[0] + ":" + i[1] + "\n"
            new_msg_history.append({"role": "assistant", "content": new_content})

    # Handle pricing for both OpenAI and OpenRouter models
    if model in OPENAI_MODELS:
        pricing = OPENAI_MODELS[model]
    else:
        # For OpenRouter, the model name is like "openai/gpt-4o-mini"
        # but pricing is stored under "openrouter/openai/gpt-4o-mini"
        openrouter_key = f"openrouter/{model}"
        if openrouter_key in OPENROUTER_MODELS:
            pricing = OPENROUTER_MODELS[openrouter_key]
        else:
            logger.warning(f"Unknown model for pricing: {model}, using zero cost")
            pricing = {"input_price": 0, "output_price": 0}

    input_cost = pricing["input_price"] * input_tokens
    output_cost = pricing["output_price"] * output_tokens
    result = QueryResult(
        content=content,
        msg=msg,
        system_msg=system_msg,
        new_msg_history=new_msg_history,
        model_name=model,
        kwargs=kwargs,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=input_cost + output_cost,
        input_cost=input_cost,
        output_cost=output_cost,
        thought=thought,
        tool_calls=tool_calls,
        model_posteriors=model_posteriors,
    )
    return result
