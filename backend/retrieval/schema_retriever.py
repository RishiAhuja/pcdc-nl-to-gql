"""
Schema Retriever — finds relevant PCDC field definitions
from ChromaDB based on semantic similarity.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from retrieval.client import (
    get_chroma_client,
    get_embedding_client,
    SCHEMA_COLLECTION,
)


@dataclass
class SchemaField:
    """A single PCDC field with its metadata."""
    field_name: str
    nested_path: str        # empty string if flat
    field_type: str          # "enum" or "numeric"
    valid_values: list[str]  # enum values, empty for numeric
    description: str         # human-readable description used as the embedded doc


class SchemaRetriever:
    """Retrieves the most relevant PCDC schema field definitions."""

    def retrieve(self, query: str, n_results: int = 8) -> list[SchemaField]:
        """Return the top-k most relevant schema fields for a query."""
        chroma = get_chroma_client()
        collection_id = chroma.get_or_create_collection(SCHEMA_COLLECTION)

        embedding = get_embedding_client().embed_one(query)
        results = chroma.query(
            collection_id=collection_id,
            query_embeddings=[embedding],
            n_results=n_results,
        )

        fields: list[SchemaField] = []
        if not results.get("metadatas") or not results["metadatas"][0]:
            return fields

        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            values = json.loads(meta.get("valid_values", "[]"))
            fields.append(
                SchemaField(
                    field_name=meta["field_name"],
                    nested_path=meta.get("nested_path", ""),
                    field_type=meta.get("field_type", "enum"),
                    valid_values=values,
                    description=doc,
                )
            )

        return fields

    def format_for_prompt(self, fields: list[SchemaField]) -> str:
        """Format retrieved fields for inclusion in the LLM prompt."""
        lines: list[str] = []
        for i, f in enumerate(fields, 1):
            path_info = f"Nested in: {f.nested_path}" if f.nested_path else "Flat field (subject-level)"
            vals = ", ".join(f.valid_values[:30])  # cap display
            if len(f.valid_values) > 30:
                vals += f", ... ({len(f.valid_values)} total)"

            lines.append(
                f"{i}. **{f.field_name}**\n"
                f"   {path_info}\n"
                f"   Type: {f.field_type}\n"
                f"   Valid values: [{vals}]"
            )
        return "\n\n".join(lines)
