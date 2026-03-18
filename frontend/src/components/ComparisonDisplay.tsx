import { ArrowLeftRight, Plus, Minus, RefreshCw } from "lucide-react";
import type { ComparisonResult, FieldDiff } from "../types";

interface Props {
  comparison: ComparisonResult;
}

function DiffIcon({ status }: { status: FieldDiff["status"] }) {
  switch (status) {
    case "added":
      return <Plus className="w-3 h-3 text-emerald-600" />;
    case "removed":
      return <Minus className="w-3 h-3 text-red-500" />;
    case "changed":
      return <RefreshCw className="w-3 h-3 text-amber-600" />;
  }
}

function diffColor(status: FieldDiff["status"]) {
  switch (status) {
    case "added":
      return "bg-emerald-50 border-emerald-200 text-emerald-800";
    case "removed":
      return "bg-red-50 border-red-200 text-red-800";
    case "changed":
      return "bg-amber-50 border-amber-200 text-amber-800";
  }
}

function diffLabel(status: FieldDiff["status"]) {
  switch (status) {
    case "added":
      return "Only in B";
    case "removed":
      return "Only in A";
    case "changed":
      return "Changed";
  }
}

export default function ComparisonDisplay({ comparison }: Props) {
  const grouped = {
    changed: comparison.diffs.filter((d) => d.status === "changed"),
    added: comparison.diffs.filter((d) => d.status === "added"),
    removed: comparison.diffs.filter((d) => d.status === "removed"),
  };

  return (
    <div className="mt-3 rounded-xl border border-gray-200 overflow-hidden shadow-card">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-slate-50 border-b border-gray-200">
        <ArrowLeftRight className="w-3.5 h-3.5 text-slate-700" />
        <span className="text-xs font-semibold text-slate-700">
          Cohort Comparison
        </span>
        <span className="text-[10px] text-gray-400 ml-auto">
          {comparison.diffs.length} difference
          {comparison.diffs.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Names */}
      <div className="grid grid-cols-2 gap-px bg-gray-100">
        <div className="bg-white px-4 py-2">
          <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">
            Filter A
          </span>
          <p className="text-xs font-medium text-slate-800 mt-0.5 truncate">
            {comparison.filter_a_name}
          </p>
        </div>
        <div className="bg-white px-4 py-2">
          <span className="text-[10px] uppercase tracking-wide text-gray-400 font-medium">
            Filter B
          </span>
          <p className="text-xs font-medium text-slate-800 mt-0.5 truncate">
            {comparison.filter_b_name}
          </p>
        </div>
      </div>

      {/* Diffs */}
      {comparison.diffs.length === 0 ? (
        <div className="px-4 py-4 text-center text-xs text-gray-400">
          The two filters are identical.
        </div>
      ) : (
        <div className="px-3 py-2.5 space-y-1.5">
          {(["changed", "removed", "added"] as const).map((status) =>
            grouped[status].map((diff, i) => (
              <div
                key={`${status}-${i}`}
                className={`flex items-start gap-2 px-3 py-2 rounded-lg border text-xs ${diffColor(
                  status
                )}`}
              >
                <DiffIcon status={status} />
                <div className="flex-1 min-w-0">
                  <span className="font-mono font-medium">{diff.field}</span>
                  <span className="text-[10px] ml-1.5 opacity-70">
                    ({diffLabel(status)})
                  </span>
                  {status === "changed" && (
                    <div className="flex items-center gap-2 mt-1 text-[10px]">
                      <span className="line-through opacity-60">
                        {String(diff.value_a)}
                      </span>
                      <span>→</span>
                      <span className="font-medium">{String(diff.value_b)}</span>
                    </div>
                  )}
                  {status === "removed" && diff.value_a != null && (
                    <div className="mt-0.5 text-[10px] opacity-70">
                      {String(diff.value_a)}
                    </div>
                  )}
                  {status === "added" && diff.value_b != null && (
                    <div className="mt-0.5 text-[10px] opacity-70">
                      {String(diff.value_b)}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
