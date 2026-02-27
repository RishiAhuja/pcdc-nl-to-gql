"""
GQL filter validator — checks generated filters against the PCDC schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from config import get_settings


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields_used: list[str] = field(default_factory=list)


class GQLFilterValidator:
    """Validates a Guppy GQL filter JSON against the PCDC schema."""

    def __init__(self) -> None:
        s = get_settings()

        with open(s.resolve_path(s.processed_gitops_json)) as f:
            self._field_to_paths: dict[str, list[str]] = json.load(f)

        with open(s.resolve_path(s.processed_schema_json)) as f:
            enum_to_fields: dict[str, list[str]] = json.load(f)

        # Build reverse map: field_name → set of valid enum values
        self._field_to_enums: dict[str, set[str]] = {}
        for enum_val, field_names in enum_to_fields.items():
            for fn in field_names:
                if fn not in self._field_to_enums:
                    self._field_to_enums[fn] = set()
                self._field_to_enums[fn].add(enum_val)

        self._all_fields = set(self._field_to_paths.keys())
        # disease_phase is a special anchor field always valid inside nested
        self._all_fields.add("disease_phase")

    def validate(self, gql_filter: dict[str, Any]) -> ValidationResult:
        """Validate a GQL filter object. Returns validation result."""
        result = ValidationResult()
        self._check_node(gql_filter, result, current_nested_path="")
        result.is_valid = len(result.errors) == 0
        return result

    def _check_node(
        self,
        node: dict[str, Any],
        result: ValidationResult,
        current_nested_path: str,
    ) -> None:
        if not isinstance(node, dict):
            result.errors.append(f"Expected dict, got {type(node).__name__}")
            return

        for key, value in node.items():
            if key in ("AND", "OR"):
                if not isinstance(value, list):
                    result.errors.append(f"'{key}' must be a list, got {type(value).__name__}")
                    continue
                for child in value:
                    self._check_node(child, result, current_nested_path)

            elif key == "nested":
                self._check_nested(value, result)

            elif key in ("IN", "in"):
                self._check_in(value, result, current_nested_path)

            elif key in ("=", "eq", "EQ", "!="):
                self._check_equality(value, result)

            elif key in (">", ">=", "<", "<=", "GT", "GTE", "LT", "LTE", "gt", "gte", "lt", "lte"):
                self._check_comparison(value, result)

            elif key == "search":
                pass  # text search — always valid structurally

            else:
                result.warnings.append(f"Unknown operator: '{key}'")

    def _check_nested(self, value: dict[str, Any], result: ValidationResult) -> None:
        if not isinstance(value, dict):
            result.errors.append("'nested' value must be a dict")
            return

        path = value.get("path")
        if not path:
            result.errors.append("'nested' must have a 'path' key")
            return

        # Validate the nested path exists in our schema
        valid_paths = set()
        for field_name, paths in self._field_to_paths.items():
            for p in paths:
                valid_paths.add(p)

        if path not in valid_paths:
            result.errors.append(
                f"Invalid nested path: '{path}'. "
                f"Valid paths: {sorted(valid_paths)}"
            )

        # Check children within this nested path context
        for key in ("AND", "OR"):
            if key in value:
                for child in value[key]:
                    self._check_node(child, result, current_nested_path=path)

    def _check_in(
        self,
        value: dict[str, Any],
        result: ValidationResult,
        nested_path: str,
    ) -> None:
        if not isinstance(value, dict):
            result.errors.append("'IN' value must be a dict")
            return

        for field_name, values in value.items():
            result.fields_used.append(field_name)

            if field_name not in self._all_fields:
                result.errors.append(
                    f"Unknown field: '{field_name}'. Did you mean one of: "
                    f"{self._suggest_field(field_name)}?"
                )
                continue

            if not isinstance(values, list):
                result.errors.append(f"IN values for '{field_name}' must be a list")
                continue

            # Check that the field belongs to the current nested path
            if nested_path:
                expected_paths = self._field_to_paths.get(field_name, [])
                if expected_paths and nested_path not in expected_paths:
                    if field_name != "disease_phase":  # anchor is always ok
                        result.errors.append(
                            f"Field '{field_name}' should be in nested path "
                            f"'{expected_paths}', but found in '{nested_path}'"
                        )

            # Check enum values
            valid_enums = self._field_to_enums.get(field_name)
            if valid_enums:
                for v in values:
                    if v not in valid_enums:
                        result.warnings.append(
                            f"Value '{v}' may not be valid for field '{field_name}'"
                        )

    def _check_equality(self, value: dict[str, Any], result: ValidationResult) -> None:
        if not isinstance(value, dict):
            result.errors.append("Equality operator value must be a dict")
            return
        for field_name in value:
            result.fields_used.append(field_name)
            if field_name not in self._all_fields:
                result.errors.append(f"Unknown field: '{field_name}'")

    def _check_comparison(self, value: dict[str, Any], result: ValidationResult) -> None:
        if not isinstance(value, dict):
            result.errors.append("Comparison operator value must be a dict")
            return
        for field_name, num in value.items():
            result.fields_used.append(field_name)
            if field_name not in self._all_fields:
                result.errors.append(f"Unknown field: '{field_name}'")
            if not isinstance(num, (int, float)):
                result.errors.append(
                    f"Comparison value for '{field_name}' must be numeric, got {type(num).__name__}"
                )

    def _suggest_field(self, wrong_name: str) -> str:
        """Suggest similar field names (simple substring match)."""
        lower = wrong_name.lower()
        suggestions = [
            f for f in self._all_fields
            if lower in f.lower() or f.lower() in lower
        ]
        if suggestions:
            return ", ".join(sorted(suggestions)[:5])
        return "(no close matches)"


@lru_cache()
def get_validator() -> GQLFilterValidator:
    return GQLFilterValidator()
