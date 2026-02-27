"""
LLM provider abstraction — supports OpenAI, Anthropic, and Google.
Switch via LLM_PROVIDER in .env.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from config import get_settings


@lru_cache()
def get_llm(*, streaming: bool = True) -> BaseChatModel:
    """Return a LangChain chat model for the configured provider."""
    s = get_settings()
    provider = s.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=s.llm_model,
            api_key=s.openai_api_key,
            temperature=0,
            streaming=streaming,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=s.llm_model,
            api_key=s.anthropic_api_key,
            temperature=0,
            streaming=streaming,
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=s.llm_model,
            google_api_key=s.google_api_key,
            temperature=0,
            streaming=streaming,
        )

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}")


@lru_cache()
def get_llm_json(*, streaming: bool = False) -> BaseChatModel:
    """Return an LLM configured for JSON output (non-streaming for structured)."""
    s = get_settings()
    provider = s.llm_provider.lower()

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=s.llm_model,
            api_key=s.openai_api_key,
            temperature=0,
            streaming=streaming,
            model_kwargs={"response_format": {"type": "json_object"}},
        )

    # For non-OpenAI, fall back to regular model + JSON instructions in prompt
    return get_llm(streaming=streaming)
