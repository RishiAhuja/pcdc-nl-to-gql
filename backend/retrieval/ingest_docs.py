"""
Ingest the PCDC LinkML data dictionary into a ChromaDB collection.

Parses the authoritative data_dictionary.yaml from chicagopcdc/linkml-data-dictionary
and creates one document per:
  - slot (field): name, description, range, parent class, subset membership
  - class (entity): name, description, list of slots
  - enum: name, permissible values with definitions

Run:
    cd chatbot/backend
    python -m retrieval.ingest_docs [--yaml PATH]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from config import get_settings
from retrieval.client import (
    get_chroma_client,
    get_embedding_client,
    DOCS_COLLECTION,
)

# Default path to the data dictionary YAML (relative to chatbot/)
DEFAULT_YAML = "../linkml-data-dictionary/linkml_data_dictionary/model/schema/data_dictionary.yaml"


def _parse_yaml(yaml_path: Path) -> dict:
    """Load and return the LinkML YAML as a dict."""
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_slot_documents(
    schema: dict,
    slot_to_classes: dict[str, list[str]],
) -> tuple[list[str], list[str], list[dict]]:
    """Build documents for each slot (field) definition."""
    ids, documents, metadatas = [], [], []
    slots = schema.get("slots", {})

    for slot_name, slot_def in slots.items():
        if not isinstance(slot_def, dict):
            continue

        desc = slot_def.get("description", "No description available.")
        range_info = slot_def.get("range", "string")
        required = slot_def.get("required", False)
        subsets = slot_def.get("in_subset", [])

        parent_classes = slot_to_classes.get(slot_name, [])
        parent_str = ", ".join(parent_classes) if parent_classes else "Unknown"

        # Build a rich text document for embedding
        parts = [f"{slot_name}: {desc}"]
        parts.append(f"Range/type: {range_info}.")
        if required:
            parts.append("This field is required.")
        if parent_classes:
            parts.append(f"Used in: {', '.join(parent_classes)}.")
        if subsets:
            parts.append(f"Available in consortia subsets: {', '.join(subsets)}.")

        doc_text = " ".join(parts)

        ids.append(f"slot_{slot_name}")
        documents.append(doc_text)
        metadatas.append({
            "name": slot_name,
            "doc_type": "slot",
            "description": desc,
            "parent_class": parent_str,
            "range_info": str(range_info),
            "permissible_values": "[]",
        })

    return ids, documents, metadatas


def _build_class_documents(schema: dict) -> tuple[list[str], list[str], list[dict], dict[str, list[str]]]:
    """Build documents for each class (entity) and return slot→class mapping."""
    ids, documents, metadatas = [], [], []
    slot_to_classes: dict[str, list[str]] = {}

    classes = schema.get("classes", {})

    for cls_name, cls_def in classes.items():
        if not isinstance(cls_def, dict):
            continue

        desc = cls_def.get("description", "No description available.")
        is_a = cls_def.get("is_a", "")
        slots = cls_def.get("slots", [])
        attributes = cls_def.get("attributes", {})

        # Track which class uses which slots
        for s in slots:
            slot_to_classes.setdefault(s, []).append(cls_name)

        # Build document
        slot_names = ", ".join(slots) if slots else "none"
        attr_names = ", ".join(attributes.keys()) if attributes else ""

        parts = [f"{cls_name}: {desc}"]
        if is_a:
            parts.append(f"Inherits from: {is_a}.")
        parts.append(f"Fields: {slot_names}.")
        if attr_names:
            parts.append(f"Attributes: {attr_names}.")

        doc_text = " ".join(parts)

        ids.append(f"class_{cls_name}")
        documents.append(doc_text)
        metadatas.append({
            "name": cls_name,
            "doc_type": "class",
            "description": desc,
            "parent_class": is_a,
            "range_info": "",
            "permissible_values": json.dumps(slots[:30]),
        })

    return ids, documents, metadatas, slot_to_classes


def _build_enum_documents(schema: dict) -> tuple[list[str], list[str], list[dict]]:
    """Build documents for each enum definition."""
    ids, documents, metadatas = [], [], []
    enums = schema.get("enums", {})

    for enum_name, enum_def in enums.items():
        if not isinstance(enum_def, dict):
            continue

        desc = enum_def.get("description", "")
        pv_def = enum_def.get("permissible_values", {})

        # Build permissible values list with descriptions
        pv_entries = []
        pv_names = []
        for val_name, val_def in pv_def.items():
            pv_names.append(val_name)
            val_desc = ""
            if isinstance(val_def, dict):
                val_desc = val_def.get("description", "")
            if val_desc:
                pv_entries.append(f"{val_name} ({val_desc})")
            else:
                pv_entries.append(val_name)

        # Build document text
        parts = [f"{enum_name}:"]
        if desc:
            parts.append(desc)
        if pv_entries:
            parts.append(f"Valid values: {', '.join(pv_entries[:30])}.")
            if len(pv_entries) > 30:
                parts.append(f"({len(pv_entries)} total values)")

        doc_text = " ".join(parts)

        ids.append(f"enum_{enum_name}")
        documents.append(doc_text)
        metadatas.append({
            "name": enum_name,
            "doc_type": "enum",
            "description": desc,
            "parent_class": "",
            "range_info": "enumeration",
            "permissible_values": json.dumps(pv_names[:50]),
        })

    return ids, documents, metadatas


def ingest_docs(yaml_path: Path) -> int:
    """Parse the data dictionary YAML and ingest into ChromaDB. Returns doc count."""
    print(f"Loading LinkML data dictionary from: {yaml_path}")
    schema = _parse_yaml(yaml_path)

    chroma = get_chroma_client()
    embedder = get_embedding_client()
    collection_id = chroma.get_or_create_collection(DOCS_COLLECTION)

    # 1) Parse classes first (to build slot→class mapping)
    cls_ids, cls_docs, cls_metas, slot_to_classes = _build_class_documents(schema)
    print(f"   Found {len(cls_ids)} classes")

    # 2) Parse slots
    slot_ids, slot_docs, slot_metas = _build_slot_documents(schema, slot_to_classes)
    print(f"   Found {len(slot_ids)} slots")

    # 3) Parse enums
    enum_ids, enum_docs, enum_metas = _build_enum_documents(schema)
    print(f"   Found {len(enum_ids)} enums")

    # Combine all
    all_ids = cls_ids + slot_ids + enum_ids
    all_docs = cls_docs + slot_docs + enum_docs
    all_metas = cls_metas + slot_metas + enum_metas

    print(f"\n   Total documents to ingest: {len(all_ids)}")

    # Batch embed + upsert
    BATCH = 50
    total_batches = (len(all_ids) + BATCH - 1) // BATCH
    for i in range(0, len(all_ids), BATCH):
        batch_docs = all_docs[i : i + BATCH]
        batch_embeddings = embedder.embed(batch_docs)
        chroma.upsert(
            collection_id=collection_id,
            ids=all_ids[i : i + BATCH],
            embeddings=batch_embeddings,
            documents=batch_docs,
            metadatas=all_metas[i : i + BATCH],
        )
        print(f"   batch {i // BATCH + 1}/{total_batches}")

    return len(all_ids)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Ingest PCDC LinkML data dictionary into ChromaDB"
    )
    parser.add_argument(
        "--yaml",
        type=Path,
        default=None,
        help=f"Path to data_dictionary.yaml (default: {DEFAULT_YAML})",
    )
    args = parser.parse_args()

    settings = get_settings()

    if args.yaml:
        yaml_path = args.yaml.resolve()
    else:
        yaml_path = settings.resolve_path(DEFAULT_YAML)

    if not yaml_path.exists():
        print(f"ERROR: YAML not found at {yaml_path}")
        print("Clone the repo: git clone https://github.com/chicagopcdc/linkml-data-dictionary")
        sys.exit(1)

    print("── Ingesting PCDC data dictionary ─────────────────")
    n = ingest_docs(yaml_path)
    print(f"\n   ✓ {n} documents ingested into '{DOCS_COLLECTION}'")
    print(f"   ChromaDB at {settings.chroma_url}")


if __name__ == "__main__":
    main()
