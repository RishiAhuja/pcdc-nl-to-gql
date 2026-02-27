"""
Example Retriever — finds similar real filter sets from ChromaDB
to use as in-context few-shot examples.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from retrieval.client import (
    get_chroma_client,
    get_embedding_client,
    EXAMPLE_COLLECTION,
)


@dataclass
class FilterExample:
    """A single real filter set from the PCDC portal."""
    name: str
    nl_description: str         # natural language description
    graphql_filter: dict[str, Any]  # the target GQL filter JSON
    distance: float             # similarity distance (lower = more similar)


class ExampleRetriever:
    """Retrieves the most similar real filter sets for few-shot prompting."""

    def retrieve(self, query: str, n_results: int = 5) -> list[FilterExample]:
        """Return the top-k most similar real filter set examples."""
        chroma = get_chroma_client()
        collection_id = chroma.get_or_create_collection(EXAMPLE_COLLECTION)

        embedding = get_embedding_client().embed_one(query)
        results = chroma.query(
            collection_id=collection_id,
            query_embeddings=[embedding],
            n_results=n_results,
        )

        examples: list[FilterExample] = []
        if not results.get("metadatas") or not results["metadatas"][0]:
            return examples

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            try:
                gql = json.loads(meta.get("graphql", "{}"))
            except (json.JSONDecodeError, TypeError):
                gql = {}

            examples.append(
                FilterExample(
                    name=meta.get("name", ""),
                    nl_description=doc,
                    graphql_filter=gql,
                    distance=dist,
                )
            )

        return examples

    def format_for_prompt(self, examples: list[FilterExample]) -> str:
        """Format retrieved examples for inclusion in the LLM prompt."""
        lines: list[str] = []
        for i, ex in enumerate(examples, 1):
            gql_str = json.dumps(ex.graphql_filter, indent=2)
            lines.append(
                f"Example {i} — \"{ex.nl_description}\"\n"
                f"```json\n{gql_str}\n```"
            )
        return "\n\n".join(lines)
