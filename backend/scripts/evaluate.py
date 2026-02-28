"""
Evaluation harness for the PCDC NL-to-GraphQL pipeline.

Runs the held-out test set (data/test.csv) through the live agent and
measures field-level precision, recall, F1, structural match, value
accuracy, and validator pass rate.

IMPORTANT: Run after re-ingesting ChromaDB with data/train.csv only,
           otherwise evaluation is contaminated by train examples.

Usage:
    cd chatbot/backend
    python -m scripts.evaluate                     # sample 100 from test.csv
    python -m scripts.evaluate --all               # full test set (~300)
    python -m scripts.evaluate --n 50              # first N examples
    python -m scripts.evaluate --csv data/test.csv --n 50
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Project imports ──────────────────────────────────────────────────────────
# Must run from chatbot/backend/

try:
    from agent.graph import agent_graph
except ImportError as e:
    print(f"Import error: {e}")
    print("Run this script from the chatbot/backend/ directory:")
    print("  cd chatbot/backend && python -m scripts.evaluate")
    sys.exit(1)

# ── Constants ────────────────────────────────────────────────────────────────

SEED = 42
DEFAULT_SAMPLE = 100
DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "test.csv"


# ── Field extraction ─────────────────────────────────────────────────────────

def extract_fields(filter_obj: dict[str, Any]) -> set[str]:
    """Recursively extract all field names used in a Guppy filter JSON."""
    fields: set[str] = set()

    if not isinstance(filter_obj, dict):
        return fields

    for key, value in filter_obj.items():
        if key in ("AND", "OR"):
            if isinstance(value, list):
                for clause in value:
                    fields |= extract_fields(clause)
        elif key == "nested":
            if isinstance(value, dict):
                fields |= extract_fields(value)
        elif key in ("IN", "GTE", "LTE", "NOT"):
            if isinstance(value, dict):
                fields |= set(value.keys()) - {"path"}
        elif key == "path":
            pass  # skip path values
        else:
            # Unknown operator — still try to recurse
            if isinstance(value, dict):
                fields |= extract_fields(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        fields |= extract_fields(item)

    return fields


def extract_field_values(filter_obj: dict[str, Any]) -> dict[str, set]:
    """Extract {field_name: set of values} from a filter."""
    result: dict[str, set] = {}

    if not isinstance(filter_obj, dict):
        return result

    for key, value in filter_obj.items():
        if key in ("AND", "OR"):
            if isinstance(value, list):
                for clause in value:
                    for f, vals in extract_field_values(clause).items():
                        result.setdefault(f, set()).update(vals)
        elif key == "nested":
            if isinstance(value, dict):
                for f, vals in extract_field_values(value).items():
                    result.setdefault(f, set()).update(vals)
        elif key == "IN":
            if isinstance(value, dict):
                for fname, fvals in value.items():
                    if isinstance(fvals, list):
                        result.setdefault(fname, set()).update(str(v) for v in fvals)
        elif key in ("GTE", "LTE"):
            if isinstance(value, dict):
                for fname, fval in value.items():
                    result.setdefault(fname, set()).add(str(fval))

    return result


# ── Metrics ──────────────────────────────────────────────────────────────────

@dataclass
class ExampleResult:
    idx: int
    query: str
    gt_fields: set[str]
    gen_fields: set[str]
    gt_values: dict[str, set]
    gen_values: dict[str, set]
    validator_passed_first: bool
    retries: int = 0
    error: str | None = None   # None | "clarification_asked" | "no_filter_generated" | <exception text>

    @property
    def asked_clarification(self) -> bool:
        return self.error == "clarification_asked"

    @property
    def precision(self) -> float:
        if not self.gen_fields:
            return 0.0
        return len(self.gen_fields & self.gt_fields) / len(self.gen_fields)

    @property
    def recall(self) -> float:
        if not self.gt_fields:
            return 0.0
        return len(self.gen_fields & self.gt_fields) / len(self.gt_fields)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)

    @property
    def value_accuracy(self) -> float:
        """Of the matching fields, what fraction of values exactly match?"""
        matching_fields = self.gen_fields & self.gt_fields
        if not matching_fields:
            return 0.0
        correct = 0
        for f in matching_fields:
            if self.gt_values.get(f) == self.gen_values.get(f):
                correct += 1
        return correct / len(matching_fields)


@dataclass
class EvalSummary:
    results: list[ExampleResult] = field(default_factory=list)

    def add(self, r: ExampleResult) -> None:
        self.results.append(r)

    def _valid(self) -> list[ExampleResult]:
        return [r for r in self.results if r.error is None]

    def _clarifications(self) -> list[ExampleResult]:
        return [r for r in self.results if r.asked_clarification]

    def _hard_errors(self) -> list[ExampleResult]:
        return [r for r in self.results if r.error and not r.asked_clarification]

    def _avg(self, attr: str) -> float:
        items = self._valid()
        if not items:
            return 0.0
        return sum(getattr(r, attr) for r in items) / len(items)

    def print_report(self) -> None:
        total = len(self.results)
        valid = len(self._valid())
        clarifications = len(self._clarifications())
        hard_errors = len(self._hard_errors())

        print("\n" + "═" * 60)
        print("  EVALUATION RESULTS")
        print("═" * 60)
        print(f"  Total examples:       {total}")
        print(f"  Filter generated:     {valid}")
        print(f"  Clarification asked:  {clarifications}  (agent correctly deferred)")
        print(f"  Hard errors:          {hard_errors}")
        print()
        print(f"  Field Precision:      {self._avg('precision'):.3f}")
        print(f"  Field Recall:         {self._avg('recall'):.3f}")
        print(f"  Field F1:             {self._avg('f1'):.3f}")
        print(f"  Value Accuracy:       {self._avg('value_accuracy'):.3f}")
        vpr = sum(1 for r in self._valid() if r.validator_passed_first) / max(valid, 1)
        print(f"  Validator 1st-pass:   {vpr:.3f}  ({sum(1 for r in self._valid() if r.validator_passed_first)}/{valid})")

        # Self-healing stats
        retried = [r for r in self._valid() if r.retries > 0]
        if retried:
            avg_retries = sum(r.retries for r in retried) / len(retried)
            print(f"\n  Self-healing (retries > 0):  {len(retried)} queries")
            print(f"  Avg retries among retried:   {avg_retries:.2f}")
        else:
            print(f"\n  Self-healing retries:  0  (all generated correctly first pass)")

        print("═" * 60)

        # Per-quartile breakdown
        valid_results = self._valid()
        if valid_results:
            f1_scores = sorted(r.f1 for r in valid_results)
            n = len(f1_scores)
            print(f"\n  F1 distribution:")
            print(f"    min:   {f1_scores[0]:.3f}")
            print(f"    p25:   {f1_scores[n // 4]:.3f}")
            print(f"    p50:   {f1_scores[n // 2]:.3f}")
            print(f"    p75:   {f1_scores[3 * n // 4]:.3f}")
            print(f"    max:   {f1_scores[-1]:.3f}")

            perfect = sum(1 for s in f1_scores if s == 1.0)
            zero = sum(1 for s in f1_scores if s == 0.0)
            print(f"\n  Perfect F1=1.0:    {perfect} ({100*perfect/n:.1f}%)")
            print(f"  F1=0 (total miss): {zero} ({100*zero/n:.1f}%)")


# ── Runner ───────────────────────────────────────────────────────────────────

def run_one(query: str, idx: int) -> ExampleResult:
    """Run a single query through the agent and return the result."""
    initial_state = {
        "messages": [{"role": "user", "content": query}],
        "user_query": query,
        "conversation_id": f"eval_{idx}",
        "generation_attempts": 0,
        "needs_clarification": False,
    }

    try:
        final = agent_graph.invoke(initial_state)
        gen_filter = final.get("filter_result")
        is_valid = final.get("is_valid", False)
        attempts = final.get("generation_attempts", 0)
        needs_clarification = final.get("needs_clarification", False)

        if not isinstance(gen_filter, dict):
            # Distinguish: agent correctly asked for clarification vs genuinely failed
            error_kind = "clarification_asked" if needs_clarification else "no_filter_generated"
            return ExampleResult(
                idx=idx, query=query,
                gt_fields=set(), gen_fields=set(),
                gt_values={}, gen_values={},
                validator_passed_first=False,
                retries=max(0, attempts - 1),
                error=error_kind,
            )

        retries = max(0, attempts - 1)
        # Passed validation on first attempt → no self-healing needed
        passed_first = is_valid and retries == 0

        return ExampleResult(
            idx=idx, query=query,
            gt_fields=set(),        # filled in by caller
            gen_fields=extract_fields(gen_filter),
            gt_values={},           # filled in by caller
            gen_values=extract_field_values(gen_filter),
            validator_passed_first=passed_first,
            retries=retries,
        )
    except Exception as exc:
        return ExampleResult(
            idx=idx, query=query,
            gt_fields=set(), gen_fields=set(),
            gt_values={}, gen_values={},
            validator_passed_first=False,
            error=str(exc)[:120],
        )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the NL-to-GQL pipeline")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV,
                        help="Path to test CSV (default: data/test.csv)")
    parser.add_argument("-n", "--num", type=int, default=DEFAULT_SAMPLE, dest="n",
                        help=f"Number of examples to evaluate (default: {DEFAULT_SAMPLE})")
    parser.add_argument("--all", action="store_true",
                        help="Evaluate all examples in the test CSV")
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional JSON file to write per-example results")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Test CSV not found at {args.csv}")
        print("Run create_split.py first:")
        print("  python -m scripts.create_split")
        sys.exit(1)

    # Load test examples
    with open(args.csv, encoding="utf-8") as f:
        all_examples = [r for r in csv.DictReader(f)
                        if r.get("llm_result", "").strip() and
                           r.get("graphql_object", "").strip()]

    random.seed(args.seed)
    if args.all:
        examples = all_examples
    else:
        n = min(args.n, len(all_examples))
        examples = random.sample(all_examples, n)

    print(f"Evaluating {len(examples)} examples from {args.csv}")
    print("(Each example runs the full LangGraph pipeline — expect LLM calls)\n")

    summary = EvalSummary()
    start = time.time()

    for i, row in enumerate(examples):
        query = row["llm_result"].strip()
        gt_str = row["graphql_object"].strip()
        consortium = row.get("consortium", "_none")

        try:
            gt_filter = json.loads(gt_str)
        except json.JSONDecodeError:
            print(f"  [{i+1}/{len(examples)}] SKIP (invalid GT JSON): {query[:60]}")
            continue

        elapsed = time.time() - start  # noqa: F841 (kept for reference in future)
        print(f"  [{i+1}/{len(examples)}] {query[:70]}...", end="", flush=True)
        t0 = time.time()

        result = run_one(query, i)
        result.gt_fields = extract_fields(gt_filter)
        result.gt_values = extract_field_values(gt_filter)

        t1 = time.time()
        if result.error == "clarification_asked":
            print(f" CLARIF (agent deferred) [{t1-t0:.1f}s]")
        elif result.error:
            print(f" ERROR ({result.error}) [{t1-t0:.1f}s]")
        else:
            retry_tag = f" +{result.retries}retry" if result.retries else ""
            print(f" F1={result.f1:.2f} P={result.precision:.2f} R={result.recall:.2f}{retry_tag} [{t1-t0:.1f}s]")

        summary.add(result)

        # Brief pause to avoid rate limits
        time.sleep(0.3)

    summary.print_report()

    if args.output:
        out = []
        for r in summary.results:
            out.append({
                "idx": r.idx,
                "query": r.query[:200],
                "precision": round(r.precision, 4),
                "recall": round(r.recall, 4),
                "f1": round(r.f1, 4),
                "value_accuracy": round(r.value_accuracy, 4),
                "validator_passed_first": r.validator_passed_first,
                "retries": r.retries,
                "error": r.error,
            })
        with open(args.output, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\nPer-example results written to: {args.output}")


if __name__ == "__main__":
    main()
