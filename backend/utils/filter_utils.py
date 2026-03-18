"""
Filter comparison utility — recursively diffs two Guppy filter JSON trees.
"""

from __future__ import annotations

from typing import Any


def _extract_fields(node: Any, path: str = "") -> dict[str, Any]:
    """
    Recursively extract all field → value mappings from a Guppy filter tree.
    Returns a dict like {"sex": ["Female"], "stagings.disease_phase": ["Initial Diagnosis"]}.
    """
    fields: dict[str, Any] = {}

    if not isinstance(node, dict):
        return fields

    for key, val in node.items():
        if key in ("AND", "OR"):
            if isinstance(val, list):
                for item in val:
                    fields.update(_extract_fields(item, path))
        elif key == "nested":
            nested_path = val.get("path", "") if isinstance(val, dict) else ""
            prefix = f"{nested_path}." if nested_path else path
            for sub_key in ("AND", "OR"):
                if sub_key in val:
                    if isinstance(val[sub_key], list):
                        for item in val[sub_key]:
                            fields.update(_extract_fields(item, prefix))
        elif key == "IN":
            if isinstance(val, dict):
                for field_name, field_val in val.items():
                    full_key = f"{path}{field_name}" if path else field_name
                    fields[full_key] = sorted(field_val) if isinstance(field_val, list) else field_val
        elif key in ("GTE", "LTE", "GT", "LT"):
            if isinstance(val, dict):
                for field_name, field_val in val.items():
                    full_key = f"{path}{field_name}" if path else field_name
                    existing = fields.get(full_key, {})
                    if isinstance(existing, dict):
                        existing[key] = field_val
                    else:
                        existing = {key: field_val}
                    fields[full_key] = existing

    return fields


def diff_filters(
    filter_a: dict[str, Any],
    filter_b: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Compare two Guppy filter JSON trees and return a list of differences.

    Each diff is: {"field": str, "status": "added"|"removed"|"changed",
                   "value_a": Any|None, "value_b": Any|None}

    'added'   = present in B but not A
    'removed' = present in A but not B
    'changed' = present in both but different values
    """
    fields_a = _extract_fields(filter_a)
    fields_b = _extract_fields(filter_b)

    all_fields = sorted(set(fields_a.keys()) | set(fields_b.keys()))
    diffs: list[dict[str, Any]] = []

    for field in all_fields:
        in_a = field in fields_a
        in_b = field in fields_b

        if in_a and not in_b:
            diffs.append({
                "field": field,
                "status": "removed",
                "value_a": fields_a[field],
                "value_b": None,
            })
        elif in_b and not in_a:
            diffs.append({
                "field": field,
                "status": "added",
                "value_a": None,
                "value_b": fields_b[field],
            })
        elif fields_a[field] != fields_b[field]:
            diffs.append({
                "field": field,
                "status": "changed",
                "value_a": fields_a[field],
                "value_b": fields_b[field],
            })

    return diffs


def format_diff_summary(diffs: list[dict[str, Any]]) -> str:
    """Format diffs into a human-readable summary string for the LLM prompt."""
    if not diffs:
        return "The two filters are identical."

    lines = []
    for d in diffs:
        if d["status"] == "added":
            lines.append(f"+ ADDED in B: {d['field']} = {d['value_b']}")
        elif d["status"] == "removed":
            lines.append(f"- REMOVED from A: {d['field']} = {d['value_a']}")
        elif d["status"] == "changed":
            lines.append(f"~ CHANGED: {d['field']}: {d['value_a']} → {d['value_b']}")

    return "\n".join(lines)


def export_as_graphql(filter_json: dict[str, Any], query_type: str = "subject") -> str:
    """
    Export a Guppy filter JSON as a full GraphQL query string.
    """
    import json
    filter_str = json.dumps(filter_json, indent=2)
    return f"""query {{
  {query_type}(filter: {filter_str}, accessibility: accessible) {{
    subject_id
  }}
}}"""


def export_as_aggregation(filter_json: dict[str, Any]) -> str:
    """
    Export a Guppy filter JSON as an aggregation query.
    """
    import json
    filter_str = json.dumps(filter_json, indent=2)
    return f"""query {{
  _aggregation(filter: {filter_str}, accessibility: accessible) {{
    _totalCount
  }}
}}"""
