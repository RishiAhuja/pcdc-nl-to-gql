"""
Stratified train/test split for the PCDC filter set evaluation.

Splits the annotated dataset 80/20 with stratification by consortium
so that every disease group (INRG, INSTRuCT, NODAL, INTERACT, MaGIC,
and untagged cross-disease queries) is proportionally represented in
both the training set (ingested into ChromaDB) and the held-out test
set (never seen by the retriever).

Usage:
    cd chatbot/backend
    python -m scripts.create_split

Outputs:
    data/train.csv   — ~1200 rows, used for ChromaDB ingestion
    data/test.csv    — ~300  rows, held out for evaluation
"""

from __future__ import annotations

import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

SEED = 42
TEST_FRACTION = 0.20

ASSETS_CSV = Path(__file__).resolve().parent.parent.parent.parent / \
    "GSoC-Cohort-Discovery-Chatbot" / "assets" / \
    "annotated_amanuensis_search_dump-06-18-2025.csv"

OUT_DIR = Path(__file__).resolve().parent.parent / "data"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_consortium(graphql_str: str) -> str:
    """Extract the consortium tag from a graphql_object string."""
    try:
        obj = json.loads(graphql_str)
        for clause in obj.get("AND", []):
            if isinstance(clause, dict) and "IN" in clause:
                if "consortium" in clause["IN"]:
                    return clause["IN"]["consortium"][0]
    except (json.JSONDecodeError, TypeError, KeyError, IndexError):
        pass
    return "_none"


def _is_valid(row: dict) -> bool:
    """Return True if this row has both a valid GQL object and NL description."""
    gql = row.get("graphql_object", "").strip()
    nl = row.get("llm_result", "").strip()
    if not gql or gql in ("{}", "null") or not nl:
        return False
    try:
        parsed = json.loads(gql)
        return bool(parsed)
    except json.JSONDecodeError:
        return False


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    random.seed(SEED)

    # Load all valid rows
    with open(ASSETS_CSV, encoding="utf-8") as f:
        all_rows = [r for r in csv.DictReader(f) if _is_valid(r)]

    print(f"Total valid rows: {len(all_rows)}")

    # Bucket by consortium (stratum)
    strata: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        consortium = _get_consortium(row["graphql_object"])
        strata[consortium].append(row)

    print("\nStrata distribution:")
    for k, v in sorted(strata.items(), key=lambda x: -len(x[1])):
        label = k if k != "_none" else "(no consortium tag)"
        n_test = max(1, round(len(v) * TEST_FRACTION))
        print(f"  {label}: {len(v)} total → {len(v) - n_test} train, {n_test} test")

    # Stratified split
    train_rows: list[dict] = []
    test_rows: list[dict] = []

    for consortium, rows in strata.items():
        random.shuffle(rows)
        n_test = max(1, round(len(rows) * TEST_FRACTION))
        test_rows.extend(rows[:n_test])
        train_rows.extend(rows[n_test:])

    print(f"\nFinal split: {len(train_rows)} train / {len(test_rows)} test")

    # Write output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "filter_object", "graphql_object", "llm_result", "consortium"]

    def _write(path: Path, rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                row["consortium"] = _get_consortium(row["graphql_object"])
                writer.writerow(row)
        print(f"  ✓ wrote {len(rows)} rows → {path}")

    _write(OUT_DIR / "train.csv", train_rows)
    _write(OUT_DIR / "test.csv", test_rows)

    # Verify no overlap
    train_gqls = {r["graphql_object"] for r in train_rows}
    test_gqls = {r["graphql_object"] for r in test_rows}
    overlap = train_gqls & test_gqls
    # Note: a small number of identical filters may appear under different names
    print(f"\nExact GQL-level overlap between train and test: {len(overlap)}")
    if overlap:
        print("  (these are distinct rows with identical filters — acceptable)")

    print("\nDone. Run ingestion with:")
    print("  python -m retrieval.ingest --csv data/train.csv")


if __name__ == "__main__":
    main()
