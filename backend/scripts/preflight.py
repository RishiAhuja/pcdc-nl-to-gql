"""
Dry-run check for evaluate.py — verifies imports, CSV, and state keys
WITHOUT making any LLM or ChromaDB calls.
"""
import csv, json, sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

print("1. Checking imports...")
try:
    from agent.graph import agent_graph
    print("   ✓ agent_graph imported")
except Exception as e:
    print(f"   ✗ agent_graph import failed: {e}")
    sys.exit(1)

print("2. Checking test CSV...")
csv_path = BACKEND / "data" / "test.csv"
if not csv_path.exists():
    print(f"   ✗ Not found: {csv_path}")
    sys.exit(1)
with open(csv_path) as f:
    rows = [r for r in csv.DictReader(f) if r.get("llm_result","").strip() and r.get("graphql_object","").strip()]
print(f"   ✓ {len(rows)} valid rows in test.csv")
print(f"   Columns: {list(csv.DictReader(open(csv_path)).fieldnames)}")

print("3. Checking GT JSON is parseable...")
bad = 0
for r in rows:
    try:
        json.loads(r["graphql_object"])
    except:
        bad += 1
print(f"   ✓ {len(rows)-bad} parseable, {bad} invalid GT rows (will be skipped)")

print("4. Checking LangGraph state keys returned by graph...")
# Inspect graph state schema
try:
    schema = agent_graph.get_state_schema() if hasattr(agent_graph, 'get_state_schema') else None
    if schema:
        print(f"   State schema: {schema}")
    else:
        # Check nodes output keys from source
        import inspect
        from agent import nodes
        src = inspect.getsource(nodes)
        keys = []
        for k in ["filter_result", "is_valid", "generation_attempts", "needs_clarification", "response_text"]:
            if k in src:
                keys.append(k)
        print(f"   ✓ Found in nodes.py: {keys}")
except Exception as e:
    print(f"   ! Could not inspect schema: {e}")

print("5. Checking evaluate.py imports correctly...")
try:
    from scripts.evaluate import (
        extract_fields, extract_field_values,
        ExampleResult, EvalSummary, run_one
    )
    print("   ✓ All evaluate.py symbols importable")
except Exception as e:
    print(f"   ✗ evaluate.py import error: {e}")
    sys.exit(1)

print("6. Checking field extractor on a real GT row...")
sample = rows[0]
gt = json.loads(sample["graphql_object"])
fields = extract_fields(gt)
vals = extract_field_values(gt)
print(f"   Query:  {sample['llm_result'][:80]}")
print(f"   GT fields: {fields}")
print(f"   GT values: {vals}")

print("\n✅ All checks passed. Safe to run:")
print("   ./venv/bin/python -m scripts.evaluate -n 100 --output results.json")
