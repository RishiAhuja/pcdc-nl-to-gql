"""
Application configuration — reads from .env at the chatbot/ root.
"""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Embeddings
    embedding_model: str = "text-embedding-3-small"

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8100

    # Data paths (relative to chatbot/ dir)
    filter_sets_csv: str = "../GSoC-Cohort-Discovery-Chatbot/assets/annotated_amanuensis_search_dump-06-18-2025.csv"
    processed_gitops_json: str = "../GSoC-Cohort-Discovery-Chatbot/schema/processed_gitops.json"
    processed_schema_json: str = "../GSoC-Cohort-Discovery-Chatbot/schema/processed_pcdc_schema_prod.json"
    gitops_json: str = "../GSoC-Cohort-Discovery-Chatbot/schema/gitops.json"

    # Backend
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Guppy
    guppy_endpoint: str = "https://portal.pedscommons.org/guppy/graphql"

    # ── helpers ──────────────────────────────────────────────────

    @property
    def chroma_url(self) -> str:
        return f"http://{self.chroma_host}:{self.chroma_port}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve_path(self, rel: str) -> Path:
        """Resolve a path relative to the chatbot/ directory."""
        base = Path(__file__).resolve().parent.parent
        return (base / rel).resolve()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
