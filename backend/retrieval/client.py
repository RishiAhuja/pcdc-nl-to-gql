"""
ChromaDB REST client — no chromadb Python package needed.

Talks directly to the ChromaDB HTTP API (v1) so the backend works on
any Python version (including 3.14) without the pydantic-v1 shim.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import httpx
from openai import OpenAI

from config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_COLLECTION = "pcdc_schema_fields"
EXAMPLE_COLLECTION = "pcdc_filter_examples"
DOCS_COLLECTION = "pcdc_data_dictionary"


class ChromaHTTPClient:
    """Thin synchronous wrapper around the ChromaDB v1 REST API."""

    def __init__(self, host: str, port: int) -> None:
        self._base = f"http://{host}:{port}/api/v1"
        self._http = httpx.Client(timeout=30)

    def heartbeat(self) -> bool:
        try:
            r = self._http.get(f"{self._base}/heartbeat")
            return r.status_code == 200
        except Exception:
            return False

    # ── Collection helpers ──────────────────────────────────────

    def get_or_create_collection(self, name: str) -> str:
        """Return the collection UUID, creating it if needed."""
        r = self._http.post(
            f"{self._base}/collections",
            json={"name": name, "get_or_create": True},
        )
        r.raise_for_status()
        return r.json()["id"]

    def collection_count(self, collection_id: str) -> int:
        r = self._http.get(f"{self._base}/collections/{collection_id}/count")
        r.raise_for_status()
        return r.json()

    # ── Data operations ─────────────────────────────────────────

    def upsert(
        self,
        collection_id: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "ids": ids,
            "embeddings": embeddings,
            "documents": documents,
        }
        if metadatas:
            payload["metadatas"] = metadatas
        r = self._http.post(
            f"{self._base}/collections/{collection_id}/upsert",
            json=payload,
        )
        r.raise_for_status()

    def query(
        self,
        collection_id: str,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query_embeddings": query_embeddings,
            "n_results": n_results,
            "include": include or ["documents", "metadatas", "distances"],
        }
        r = self._http.post(
            f"{self._base}/collections/{collection_id}/query",
            json=payload,
        )
        r.raise_for_status()
        return r.json()


class EmbeddingClient:
    """Thin wrapper around the OpenAI Embeddings API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a list of texts."""
        response = self._client.embeddings.create(
            input=texts,
            model=self._model,
        )
        return [item.embedding for item in response.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache()
def get_chroma_client() -> ChromaHTTPClient:
    s = get_settings()
    return ChromaHTTPClient(host=s.chroma_host, port=s.chroma_port)


@lru_cache()
def get_embedding_client() -> EmbeddingClient:
    s = get_settings()
    return EmbeddingClient(api_key=s.openai_api_key, model=s.embedding_model)
