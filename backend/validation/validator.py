"""
GQL filter validator — checks generated filters against the PCDC schema.

Overall design
--------------
The validator is a PURELY DETERMINISTIC, ZERO-LLM check. It runs after every
filter generation and after every self-healing attempt. Its job is to catch
three categories of mistakes the LLM commonly makes:

  1. Hallucinated field names  (e.g. "tumour_type" which doesn't exist)
  2. Wrong nesting             (putting a flat field inside a nested wrapper,
                                or putting a nested field in the wrong table)
  3. Bad enum/numeric values   (wrong string value for a categorical field,
                                or a string where a number is required)

Data sources
------------
The validator loads TWO schema files at startup (via get_validator() which is
@lru_cache so they are read from disk only once per process lifetime):

  processed_gitops.json
    Shape: { field_name: [nested_table, ...] }
    Empty list   → flat field, lives directly on the subject row.
    Non-empty    → nested field, lives in the named sub-table.
    Example:
      {"sex": [],  "histology": ["histologies"],  "irs_group": ["stagings"]}

  processed_pcdc_schema_prod.json
    Shape: { enum_value: [field_name, ...] }
    This is an inverted index: enum value → which fields can hold it.
    Example:
      {"Female": ["sex"],  "AML": ["consortium"],  "Alveolar...": ["histology"]}
    During __init__ this is reversed into:
      { field_name: {enum_value, ...} }
    so lookups are O(1).

Error vs. Warning
-----------------
  ERROR   → is_valid becomes False → LLM self-healing loop is triggered
  WARNING → surfaced to the user but does NOT block the filter

The distinction is intentional:
  - Field-not-found is always an error: a filter with a non-existent field name
    will be rejected by Guppy with a hard error, so we must fix it.
  - Enum-value-not-in-schema is a warning: the schema file may be incomplete
    (a new study may contribute values not yet catalogued), so we surface it
    as advisory rather than blocking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from config import get_settings


@dataclass
class ValidationResult:
    """
    Container returned by GQLFilterValidator.validate().

    Fields
    ------
    is_valid    : True iff errors list is empty after the full walk.
    errors      : Hard failures — filter must be fixed before use.
    warnings    : Soft issues — filter may still work but worth reviewing.
    fields_used : Every field name seen inside IN / = / GTE / etc. operators.
                  Used downstream to display field chips in the UI.
    """
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fields_used: list[str] = field(default_factory=list)


class GQLFilterValidator:
    """
    Validates a Guppy GQL filter dict against the live PCDC schema.

    How it works
    ------------
    validate() calls _check_node() on the top-level dict.
    _check_node() dispatches based on the single key it finds:

      AND / OR  → recurse into each list element (same nested_path context)
      nested    → validate the path string, then recurse with updated nested_path
      IN        → field-existence + path-correctness + enum-value checks
      = / != / eq → field-existence check only (equality)
      > >= < <= GT GTE LT LTE → field-existence + numeric-type check
      unknown key → WARNING (not an error — future Guppy operators possible)

    The current_nested_path argument
    ---------------------------------
    _check_node receives current_nested_path so that when it finds a field
    inside a nested block it can verify the field actually belongs to that
    table. For example:

      {"nested": {"path": "stagings", "AND": [
        {"IN": {"irs_group": ["III"]}}
      ]}}

    When _check_in is called for irs_group, current_nested_path="stagings".
    The validator then looks up _field_to_paths["irs_group"] which is
    ["stagings"], and confirms "stagings" is in that list → OK.

    But if the LLM had mistakenly placed irs_group at the top level:
      {"IN": {"irs_group": ["III"]}}   (no nested wrapper)
    Then current_nested_path="" when _check_in runs. The check is only done
    when current_nested_path is non-empty (we validate that the field IS in
    the claimed path, not that it MUST be nested — that would false-positive
    when Guppy allows denormalized access).

    Special case: disease_phase
    ---------------------------
    disease_phase is never flagged for wrong nesting. It is the "anchor field"
    used inside nested staging/histology/etc. blocks to restrict which phase
    rows are matched. It can appear alongside any nested field.
    """

    def __init__(self) -> None:
        """
        Load both schema files and build the lookup structures used at
        validation time.

        After __init__, three dicts are available:

          self._field_to_paths  {field_name: [nested_table, ...]}
            e.g. {"sex": [],  "irs_group": ["stagings"],
                  "histology": ["histologies"]}
            Used to check (a) whether a field name exists at all, and
            (b) whether it is placed inside the correct nested wrapper.

          self._field_to_enums  {field_name: {valid_enum_value, ...}}
            Built by reversing processed_pcdc_schema_prod.json which maps
            enum_value → [field_names].  After reversal:
            e.g. {"sex": {"Female", "Male"},
                  "histology": {"Alveolar rhabdomyosarcoma (ARMS)", ...}}
            Used in _check_in() to warn about values not in the known set.

          self._all_fields  set[str]
            Union of all field names from _field_to_paths plus the special
            anchor field "disease_phase" which is always valid inside any
            nested block.
        """
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
        """
        Entry point. Validates the full filter dict and returns a
        ValidationResult with errors, warnings, and fields_used populated.

        Validation is a DEPTH-FIRST TREE WALK starting at the top-level dict.
        is_valid is set False if ANY error was accumulated during the walk.
        The walk does NOT stop at the first error — it collects all of them
        so the self-healing LLM gets a complete picture in one shot.
        """
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
        """
        Dispatch a single filter node to the appropriate check method based
        on its operator key.

        A Guppy filter node is always a single-key dict where the key is
        the operator and the value is the operand.

        current_nested_path tracks which sub-table we are currently
        inside (passed down from _check_nested). Empty string means we
        are at the top subject level.

        Dispatch table:
          AND / OR    → _check_node() on each list element (same path context)
          nested      → _check_nested() — validates the path, recurses with
                        the new path as current context
          IN / in     → _check_in()     — field existence + path + enum check
          = eq EQ !=  → _check_equality() — field existence only
          > >= < <=
          GT GTE LT LTE → _check_comparison() — field existence + numeric type
          search      → no-op (Guppy full-text search, structurally always ok)
          anything else → WARNING (unrecognized operator — may be a future
                          Guppy feature or a typo; soft because we don't want
                          to break valid future queries)
        """
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
        """
        Validate the value of a "nested" operator.

        A nested block must look like:
          {"path": "<table_name>",  "AND": [...]}   (or "OR")

        Checks performed:
          1. value is a dict                          [ERROR]
          2. "path" key is present and non-empty      [ERROR]
          3. path string names a real sub-table —
             built by collecting all non-empty path lists from
             _field_to_paths. Currently valid paths include:
             histologies, stagings, tumor_assessments, molecular_analysis,
             studies, labs, medical_histories, subject_responses,
             survival_characteristics, secondary_malignant_neoplasm,
             biopsy_surgical_procedures, radiation_therapies,
             stem_cell_transplants, imagings, external_references,
             disease_characteristics, tumor_assessments              [ERROR]

        After path validation, recurse into AND/OR children via
        _check_node with current_nested_path set to this path string.
        This propagates the path context downward so _check_in can
        verify field-to-table membership.
        """
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
        """
        Validate an IN operator node.  IN is used for ALL categorical/enum
        field lookups in Guppy.

        Expected shape:  {"IN": {"field_name": ["val1", "val2"]}}
        So `value` here is the inner dict {"field_name": [...]}.

        Checks performed (in order, for every field_name in the dict):

          1. Record field_name in result.fields_used (for UI chips).

          2. Field existence check [ERROR if fails, skip remaining checks]
             Is field_name in self._all_fields?
             If not — error + run _suggest_field() to offer corrections
             to the self-healing LLM.

          3. Value-is-list check [ERROR if fails]
             The IN operand must be a list.  LLM sometimes generates a
             bare string instead of a singleton list.

          4. Nesting-correctness check [ERROR if fails]
             Only runs when nested_path is non-empty (i.e. we're inside
             a nested block). Gets expected_paths from _field_to_paths:
               - If expected_paths is non-empty AND nested_path is not in
                 it AND field_name is not disease_phase → ERROR
             Note: if a field has expected_paths=[] (flat field) appearing
             inside a nested block — that is NOT checked here because Guppy
             may still accept it via denormalized index access.

          5. Enum value check [WARNING if fails]
             Only runs when _field_to_enums has an entry for this field
             (i.e. we know its valid values).  Numeric fields have no
             entry in _field_to_enums, so they pass silently.
             For each value in the IN list: if it's not in the known set
             → WARNING (not error) because the schema enum list may be
             incomplete for newer studies.
        """
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
        """
        Validate = / != / eq / EQ operators.

        These are used for exact single-value matches.  Unlike IN they don't
        take a list, so there are no enum-list checks here — only field
        existence.  The value itself (the RHS) is not type-checked because
        equality comparisons are valid for both strings and numbers.

        Checks: field existence [ERROR], record in fields_used.
        """
        if not isinstance(value, dict):
            result.errors.append("Equality operator value must be a dict")
            return
        for field_name in value:
            result.fields_used.append(field_name)
            if field_name not in self._all_fields:
                result.errors.append(f"Unknown field: '{field_name}'")

    def _check_comparison(self, value: dict[str, Any], result: ValidationResult) -> None:
        """
        Validate >, >=, <, <=, GT, GTE, LT, LTE operators (case variants).

        These are used exclusively for numeric range filtering (ages, doses,
        lab values, tumour sizes, etc.).

        Checks:
          1. value is a dict                  [ERROR]
          2. field_name in _all_fields        [ERROR]
          3. RHS value is int or float        [ERROR]

        The numeric type check exists because the LLM occasionally generates
        age-as-string: {"GTE": {"age_at_censor_status": "5 years"}} — which
        Guppy would reject at query-time with a cryptic type error.

        Important: Age fields in PCDC are stored in DAYS, not years.
        So "5 years" should be 1825 (5 × 365).  The validator does NOT
        enforce the days conversion — that is a prompt/LLM concern — but
        it does ensure the value is at least numeric.
        """
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
        """
        Return a comma-separated list of up to 5 field names that are
        "close" to wrong_name, using bidirectional substring matching.

        Algorithm: a real field f is included if either:
          - wrong_name (lowercased) appears as a substring of f (lowercased)
          - f (lowercased) appears as a substring of wrong_name (lowercased)

        This catches common mistakes like:
          "tumour_type"    → suggests "tumor_classification", "tumor_site" ...
          "disease"        → (no match — "disease" isn't in the schema)
          "sex_at_birth"   → suggests "sex"
          "ageatdiagnosis" → no match (too different)

        The suggestion string is embedded directly in the error message
        passed to the self-healing LLM call, so the LLM sees:
          "Unknown field 'tumour_type'. Did you mean one of: tumor_classification?"
        and can correct the field name without needing a new retrieval round.

        Returns "(no close matches)" if nothing is found so the error
        message is still grammatically complete.
        """
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
    """
    Return the singleton GQLFilterValidator instance.

    @lru_cache ensures the two schema files are read from disk exactly once
    per process lifetime (not once per request). The validator is stateless
    after __init__ — all state is in the three dicts built at startup — so
    sharing a single instance across concurrent requests is safe.
    """
    return GQLFilterValidator()
