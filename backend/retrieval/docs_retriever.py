"""
Documentation Retriever — answers "what does field X mean?" questions
by querying the PCDC data dictionary ChromaDB collection.

The collection is populated by `ingest_docs.py` from the LinkML data
dictionary YAML + generated markdown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from retrieval.client import (
    get_chroma_client,
    get_embedding_client,
    DOCS_COLLECTION,
)


@dataclass
class DocEntry:
    """A single data-dictionary documentation entry."""
    name: str               # field or enum name
    doc_type: str           # "slot", "class", or "enum"
    description: str        # rich human-readable description
    parent_class: str       # which class this slot belongs to (empty for enums/classes)
    range_info: str         # e.g. "DiseasePhaseEnum" or "integer"
    permissible_values: list[str]  # enum values (empty for non-enums)
    distance: float         # similarity distance


class DocsRetriever:
    """Retrieves the most relevant PCDC data dictionary entries."""

    def retrieve(self, query: str, n_results: int = 5) -> list[DocEntry]:
        """Return the top-k most relevant documentation entries."""
        chroma = get_chroma_client()
        collection_id = chroma.get_or_create_collection(DOCS_COLLECTION)

        embedding = get_embedding_client().embed_one(query)
        results = chroma.query(
            collection_id=collection_id,
            query_embeddings=[embedding],
            n_results=n_results,
        )

        entries: list[DocEntry] = []
        if not results.get("metadatas") or not results["metadatas"][0]:
            return entries

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            pv = meta.get("permissible_values", "[]")
            try:
                pv_list = json.loads(pv) if pv else []
            except (json.JSONDecodeError, TypeError):
                pv_list = []

            entries.append(
                DocEntry(
                    name=meta.get("name", ""),
                    doc_type=meta.get("doc_type", "slot"),
                    description=doc,
                    parent_class=meta.get("parent_class", ""),
                    range_info=meta.get("range_info", ""),
                    permissible_values=pv_list,
                    distance=dist,
                )
            )

        return entries

    def format_for_prompt(self, entries: list[DocEntry]) -> str:
        """Format retrieved docs for LLM prompt injection."""
        if not entries:
            return "(No matching documentation found)"

        lines: list[str] = []
        for i, e in enumerate(entries, 1):
            parts = [f"{i}. **{e.name}** ({e.doc_type})"]
            parts.append(f"   {e.description}")

            if e.parent_class:
                parts.append(f"   Used by: {e.parent_class}")
            if e.range_info:
                parts.append(f"   Range/Type: {e.range_info}")
            if e.permissible_values:
                vals = ", ".join(e.permissible_values[:15])
                if len(e.permissible_values) > 15:
                    vals += f", ... ({len(e.permissible_values)} total)"
                parts.append(f"   Valid values: [{vals}]")

            lines.append("\n".join(parts))

        return "\n\n".join(lines)
