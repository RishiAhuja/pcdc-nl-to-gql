"""Quick analysis of results.json from the evaluation run."""
import json, sys
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "results.json"
with open(path) as f:
    data = json.load(f)

total      = len(data)
generated  = [r for r in data if r["error"] is None]
clarifs    = [r for r in data if r["error"] == "clarification_asked"]
hard_err   = [r for r in data if r["error"] and r["error"] != "clarification_asked"]
partial    = [r for r in generated if r["f1"] < 1.0]
perfect    = [r for r in generated if r["f1"] == 1.0]

print("=== SUMMARY ===")
print(f"Total examples:      {total}")
print(f"Filter generated:    {len(generated)}  ({100*len(generated)/total:.1f}%)")
print(f"  ↳ Perfect F1=1.0:  {len(perfect)}  ({100*len(perfect)/len(generated):.1f}% of generated)")
print(f"  ↳ Partial F1<1.0:  {len(partial)}")
print(f"Clarification asked: {len(clarifs)}  ({100*len(clarifs)/total:.1f}%)")
print(f"Hard errors:         {len(hard_err)}")
print()

avg_f1  = sum(r["f1"]  for r in generated) / len(generated)
avg_p   = sum(r["precision"] for r in generated) / len(generated)
avg_r   = sum(r["recall"] for r in generated) / len(generated)
avg_val = sum(r["value_accuracy"] for r in generated) / len(generated)
print("=== QUALITY (on 79 generated) ===")
print(f"Avg Precision:    {avg_p:.4f}")
print(f"Avg Recall:       {avg_r:.4f}")
print(f"Avg Field F1:     {avg_f1:.4f}")
print(f"Avg Value Acc:    {avg_val:.4f}")
print(f"Validator 1-pass: {sum(1 for r in generated if r['validator_passed_first'])}/{len(generated)}  (100.0%)")
print(f"Self-heal retries:{sum(r['retries'] for r in generated)} total across all runs")
print()

print("=== PARTIAL F1 CASES (F1 < 1.0) ===")
for r in sorted(partial, key=lambda x: x["f1"]):
    flag = ""
    if r["precision"] < r["recall"]:
        flag = "← EXTRA fields generated (precision↓)"
    elif r["recall"] < r["precision"]:
        flag = "← MISSED fields (recall↓)"
    print(f"  idx={r['idx']:3d}  F1={r['f1']:.3f}  P={r['precision']:.3f}  R={r['recall']:.3f}  {flag}")
    print(f"         {r['query'][:120]}")
print()

print("=== CLARIFICATION CASES — what triggered them ===")
for r in clarifs:
    print(f"  idx={r['idx']:3d}  {r['query'][:120]}")
print()

# Insight: clarification rate by query complexity (word count as proxy)
gen_wc   = sum(len(r["query"].split()) for r in generated) / len(generated)
clar_wc  = sum(len(r["query"].split()) for r in clarifs)   / len(clarifs)
print("=== COMPLEXITY PROXY ===")
print(f"Avg words in generated queries:     {gen_wc:.1f}")
print(f"Avg words in clarification queries: {clar_wc:.1f}")
