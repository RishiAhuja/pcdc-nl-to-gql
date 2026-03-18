import { useState } from "react";
import { AlertTriangle, CheckCircle, Code2 } from "lucide-react";
import type { FilterResult } from "../types";
import ExportMenu from "./ExportMenu";
import SaveFilterButton from "./SaveFilterButton";

interface Props {
  filter: FilterResult;
  nlDescription?: string;
}

// Simple JSON syntax highlighter — returns an array of <span> elements
function highlightJson(json: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // Matches: string keys (with colon), string values, booleans, nulls, numbers, punctuation
  const re = /("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"\s*:)|("(?:\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*")|(\btrue\b|\bfalse\b)|(\bnull\b)|(-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)|([{}[\],])/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(json)) !== null) {
    if (m.index > last) nodes.push(json.slice(last, m.index));
    if (m[1]) nodes.push(<span key={m.index} className="json-key">{m[1]}</span>);
    else if (m[2]) nodes.push(<span key={m.index} className="json-string">{m[2]}</span>);
    else if (m[3]) nodes.push(<span key={m.index} className="json-bool">{m[3]}</span>);
    else if (m[4]) nodes.push(<span key={m.index} className="json-null">{m[4]}</span>);
    else if (m[5]) nodes.push(<span key={m.index} className="json-number">{m[5]}</span>);
    else nodes.push(<span key={m.index} className="json-punct">{m[0]}</span>);
    last = re.lastIndex;
  }
  if (last < json.length) nodes.push(json.slice(last));
  return nodes;
}

export default function FilterDisplay({ filter, nlDescription }: Props) {
  const jsonStr = JSON.stringify(filter.filter, null, 2);

  return (
    <div className="mt-3 rounded-xl border overflow-hidden shadow-card" style={{ borderColor: filter.isValid ? "#d1d5db" : "#e5e7eb" }}>
      {/* Header bar */}
      <div
        className="flex items-center justify-between px-3.5 py-2"
        style={{
          background: filter.isValid
            ? "#f9fafb"
            : "#f9fafb",
        }}
      >
        <div className="flex items-center gap-2">
          {filter.isValid ? (
            <CheckCircle className="w-3.5 h-3.5 text-slate-700" />
          ) : (
            <AlertTriangle className="w-3.5 h-3.5 text-slate-700" />
          )}
          <span className={`text-xs font-semibold ${
              filter.isValid ? "text-slate-700" : "text-slate-700"
            }`}>
            {filter.isValid ? "Valid Filter" : "Filter (with warnings)"}
          </span>
          <Code2 className="w-3 h-3 text-gray-400" />
          <span className="text-[10px] text-gray-400">
            Guppy GraphQL
          </span>
        </div>
        <div className="flex items-center gap-2">
          {filter.fieldsUsed.length > 0 && (
            <span className="text-[10px] text-gray-400">
              {filter.fieldsUsed.length} field{filter.fieldsUsed.length !== 1 ? "s" : ""}
            </span>
          )}
          <SaveFilterButton filter={filter.filter} explanation={nlDescription} />
          <ExportMenu filter={filter.filter} />
        </div>
      </div>

      {/* Syntax-highlighted JSON body */}
       <pre className="json-display px-4 py-3.5 overflow-x-auto max-h-72 overflow-y-auto"
         style={{ background: "#111827" }}>
        {highlightJson(jsonStr)}
      </pre>

      {/* Errors */}
      {filter.errors.length > 0 && (
        <div className="px-4 py-2.5 bg-red-50 border-t border-red-100">
          {filter.errors.map((err, i) => (
            <p key={i} className="text-xs text-red-700 flex items-start gap-1.5 mb-0.5">
              <span className="mt-0.5 flex-shrink-0">•</span>
              <span>{err}</span>
            </p>
          ))}
        </div>
      )}
      {filter.warnings.length > 0 && (
        <div className="px-4 py-2.5 bg-amber-50 border-t border-amber-100">
          {filter.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-700 flex items-start gap-1.5 mb-0.5">
              <span className="mt-0.5 flex-shrink-0">•</span>
              <span>{w}</span>
            </p>
          ))}
        </div>
      )}

      {/* Fields used chips */}
      {filter.fieldsUsed.length > 0 && (
        <div className="px-3.5 py-2.5 bg-white border-t border-gray-100 flex flex-wrap gap-1.5">
          {filter.fieldsUsed.map((f) => (
            <span
              key={f}
              className="px-2.5 py-0.5 text-[10px] font-mono font-medium rounded-full"
              style={{ background: "#f1f5f9", color: "#334155" }}
            >
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
