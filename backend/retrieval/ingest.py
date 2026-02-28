"""
One-time ingestion script — populates ChromaDB with:
  1. Schema fields (75 fields + enum values) → schema collection
  2. Real filter set examples (1,348 NL/GQL pairs) → example collection

Run:
    cd chatbot/backend
    python -m retrieval.ingest
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from config import get_settings
from retrieval.client import (
    get_chroma_client,
    get_embedding_client,
    SCHEMA_COLLECTION,
    EXAMPLE_COLLECTION,
)

# ── Numeric fields (we know these from the data model) ───────────
NUMERIC_FIELDS = {
    "year_at_disease_phase",
    "age_at_censor_status",
    "age_at_tumor_assessment",
    "age_at_molecular_analysis",
    "age_at_smn",
    "age_at_lkss",
    "longest_diam_dim1",
    "depth",
    "tumor_size",
    "rt_dose",
    "lab_result_numeric",
    "necrosis_pct",
    "dna_index",
    "lkss",
    "lkss_obfuscated",
}


def _build_field_enum_map(
    processed_schema: dict[str, list[str]],
    processed_gitops: dict[str, list[str]],
) -> dict[str, list[str]]:
    """
    Build a mapping: field_name → [list of valid enum values].

    processed_schema maps enum_value → [field_names].
    We reverse it to field_name → [enum_values].
    """
    field_to_enums: dict[str, list[str]] = defaultdict(list)
    for enum_val, field_names in processed_schema.items():
        for fn in field_names:
            # Only include if the field exists in our gitops config
            if fn in processed_gitops:
                field_to_enums[fn].append(enum_val)

    return dict(field_to_enums)


def _build_field_description(
    field_name: str,
    nested_path: str,
    field_type: str,
    enum_values: list[str],
) -> str:
    """Build a rich text description of a field for embedding."""
    parts = [f"{field_name}:"]

    # Human-friendly name
    human_name = field_name.replace("_", " ").title()
    parts.append(f"{human_name}.")

    if nested_path:
        parts.append(f"This field is nested inside the '{nested_path}' table.")
    else:
        parts.append("This is a subject-level (flat) field.")

    if field_type == "numeric":
        parts.append("This is a numeric field. Use GTE/LTE operators for ranges.")
    elif enum_values:
        # Show a sample of values for embedding quality
        sample = enum_values[:20]
        parts.append(f"Valid values include: {', '.join(sample)}.")
        if len(enum_values) > 20:
            parts.append(f"({len(enum_values)} total values)")

    return " ".join(parts)


def ingest_schema(
    processed_gitops: dict[str, list[str]],
    processed_schema: dict[str, list[str]],
) -> int:
    """Populate the schema collection. Returns count of documents added."""
    chroma = get_chroma_client()
    embedder = get_embedding_client()

    # get_or_create — upsert with fixed IDs overwrites on re-run
    collection_id = chroma.get_or_create_collection(SCHEMA_COLLECTION)

    field_to_enums = _build_field_enum_map(processed_schema, processed_gitops)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for field_name, paths in processed_gitops.items():
        nested_path = paths[0] if paths else ""
        is_numeric = field_name in NUMERIC_FIELDS
        field_type = "numeric" if is_numeric else "enum"
        enum_values = field_to_enums.get(field_name, [])

        description = _build_field_description(
            field_name, nested_path, field_type, enum_values
        )

        ids.append(f"field_{field_name}")
        documents.append(description)
        metadatas.append({
            "field_name": field_name,
            "nested_path": nested_path,
            "field_type": field_type,
            "valid_values": json.dumps(enum_values),
        })

    # Batch: embed then upsert
    BATCH = 50  # keep OpenAI batch size reasonable
    for i in range(0, len(ids), BATCH):
        batch_docs = documents[i : i + BATCH]
        batch_embeddings = embedder.embed(batch_docs)
        chroma.upsert(
            collection_id=collection_id,
            ids=ids[i : i + BATCH],
            embeddings=batch_embeddings,
            documents=batch_docs,
            metadatas=metadatas[i : i + BATCH],
        )
        print(f"   schema batch {i // BATCH + 1}/{(len(ids) + BATCH - 1) // BATCH}")

    return len(ids)


def ingest_examples(csv_path: Path) -> int:
    """Populate the example collection from the annotated CSV. Returns count."""
    chroma = get_chroma_client()
    embedder = get_embedding_client()

    # get_or_create — upsert with fixed IDs overwrites on re-run
    collection_id = chroma.get_or_create_collection(EXAMPLE_COLLECTION)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            # Skip rows without valid GQL
            gql_str = row.get("graphql_object", "").strip()
            if not gql_str or gql_str in ("{}", "null"):
                continue

            try:
                gql = json.loads(gql_str)
            except json.JSONDecodeError:
                continue

            # Skip trivially empty filters
            if not gql:
                continue

            nl = row.get("llm_result", "").strip()
            name = row.get("name", f"filter_{idx}")

            if not nl:
                continue

            ids.append(f"example_{idx}")
            documents.append(nl)
            metadatas.append({
                "name": name,
                "graphql": json.dumps(gql),
            })

    # Batch: embed then upsert
    BATCH = 50
    total_batches = (len(ids) + BATCH - 1) // BATCH
    for i in range(0, len(ids), BATCH):
        batch_docs = documents[i : i + BATCH]
        batch_embeddings = embedder.embed(batch_docs)
        chroma.upsert(
            collection_id=collection_id,
            ids=ids[i : i + BATCH],
            embeddings=batch_embeddings,
            documents=batch_docs,
            metadatas=metadatas[i : i + BATCH],
        )
        print(f"   examples batch {i // BATCH + 1}/{total_batches}")

    return len(ids)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ingest schema and filter-set examples into ChromaDB")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help=(
            "Path to the filter-set CSV to ingest. "
            "Defaults to the path configured in config.py (full dataset). "
            "Pass data/train.csv here to ingest only the training split."
        ),
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip schema field ingestion (useful when only re-ingesting examples).",
    )
    parser.add_argument(
        "--skip-examples",
        action="store_true",
        help="Skip example ingestion.",
    )
    args = parser.parse_args()

    settings = get_settings()

    gitops_path = settings.resolve_path(settings.processed_gitops_json)
    schema_path = settings.resolve_path(settings.processed_schema_json)

    # --csv overrides the default configured path
    if args.csv is not None:
        csv_path = Path(args.csv).resolve()
    else:
        csv_path = settings.resolve_path(settings.filter_sets_csv)

    print(f"Loading processed_gitops from: {gitops_path}")
    with open(gitops_path) as f:
        processed_gitops = json.load(f)

    print(f"Loading processed_schema from: {schema_path}")
    with open(schema_path) as f:
        processed_schema = json.load(f)

    print(f"Loading filter sets CSV from: {csv_path}")

    if not args.skip_schema:
        print("\n── Ingesting schema fields ─────────────────────")
        n_schema = ingest_schema(processed_gitops, processed_schema)
        print(f"   ✓ {n_schema} schema fields ingested into '{SCHEMA_COLLECTION}'")
    else:
        print("\n── Skipping schema field ingestion (--skip-schema) ─")
        n_schema = 0

    if not args.skip_examples:
        print("\n── Ingesting filter set examples ───────────────")
        n_examples = ingest_examples(csv_path)
        print(f"   ✓ {n_examples} examples ingested into '{EXAMPLE_COLLECTION}'")
    else:
        print("\n── Skipping example ingestion (--skip-examples) ─")
        n_examples = 0

    print("\n── Done! ──────────────────────────────────────")
    if n_schema + n_examples > 0:
        print(f"ChromaDB at {settings.chroma_url} now has {n_schema + n_examples} total documents.")


if __name__ == "__main__":
    main()
