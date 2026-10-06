from typing import Any, Tuple
import os
import anthropic
import openai
import instructor
from pathlib import Path
from dotenv import load_dotenv
from .models.pricing import (
    CLAUDE_MODELS,
    BEDROCK_MODELS,
    OPENAI_MODELS,
    DEEPSEEK_MODELS,
    GEMINI_MODELS,
    OPENROUTER_MODELS,
)

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


def get_client_llm(model_name: str, structured_output: bool = False) -> Tuple[Any, str]:
    """Get the client and model for the given model name.

    Args:
        model_name (str): The name of the model to get the client.

    Raises:
        ValueError: If the model is not supported.

    Returns:
        The client and model for the given model name.
    """
    # print(f"Getting client for model {model_name}")
    if model_name.startswith("openrouter/"):
        # For OpenRouter, we use the OpenAI client but with a different base URL
        # and API key.
        # Check https://openrouter.ai/models for a full list of supported models.
        # Alternatively, libraries like Vercel AI SDK or Model.dev maintain lists
        # of models with their capabilities, strengths, and pricing.

        # Remove the prefix for the actual API call if needed,
        # but OpenRouter expects the full "vendor/model" string usually.
        # However, checking the OpenRouter docs, they often accept 'anthropic/claude-3-5-sonnet'
        # So we might need to strip 'openrouter/' but keep the vendor prefix.

        actual_model_name = model_name.replace("openrouter/", "")

        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
        if structured_output:
            # Instructor works with any OpenAI-compatible client
            client = instructor.from_openai(client, mode=instructor.Mode.TOOLS_STRICT)

        return client, actual_model_name

    if model_name in CLAUDE_MODELS.keys():
        client = anthropic.Anthropic()
        if structured_output:
            client = instructor.from_anthropic(
                client, mode=instructor.mode.Mode.ANTHROPIC_JSON
            )
    elif model_name in BEDROCK_MODELS.keys():
        model_name = model_name.split("/")[-1]
        client = anthropic.AnthropicBedrock(
            aws_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_region=os.getenv("AWS_REGION_NAME"),
        )
        if structured_output:
            client = instructor.from_anthropic(
                client, mode=instructor.mode.Mode.ANTHROPIC_JSON
            )
    elif model_name in OPENAI_MODELS.keys():
        client = openai.OpenAI()
        if structured_output:
            client = instructor.from_openai(client, mode=instructor.Mode.TOOLS_STRICT)
    elif model_name.startswith("azure-"):
        # get rid of the azure- prefix
        model_name = model_name.split("azure-")[-1]
        client = openai.AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_API_VERSION"),
            azure_endpoint=os.getenv("AZURE_API_ENDPOINT"),
        )
        if structured_output:
            client = instructor.from_openai(client, mode=instructor.Mode.TOOLS_STRICT)
    elif model_name in DEEPSEEK_MODELS.keys():
        client = openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url="https://api.deepseek.com",
        )
        if structured_output:
            client = instructor.from_openai(client, mode=instructor.Mode.MD_JSON)
    elif model_name in GEMINI_MODELS.keys():
        client = openai.OpenAI(
            api_key=os.environ["GEMINI_API_KEY"],
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        if structured_output:
            client = instructor.from_openai(
                client,
                mode=instructor.Mode.GEMINI_JSON,
            )
    else:
        raise ValueError(f"Model {model_name} not supported.")

    return client, model_name
