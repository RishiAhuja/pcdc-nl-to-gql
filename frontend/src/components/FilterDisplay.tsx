import { useState } from "react";
import { Check, Copy, AlertTriangle, CheckCircle } from "lucide-react";
import type { FilterResult } from "../types";

interface Props {
  filter: FilterResult;
}

export default function FilterDisplay({ filter }: Props) {
  const [copied, setCopied] = useState(false);

  const jsonStr = JSON.stringify(filter.filter, null, 2);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(jsonStr);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-3 rounded-lg border border-gray-200 overflow-hidden">
      {/* Header bar */}
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          {filter.isValid ? (
            <CheckCircle className="w-4 h-4 text-green-600" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-amber-500" />
          )}
          <span
            className={`text-xs font-medium ${
              filter.isValid ? "text-green-700" : "text-amber-600"
            }`}
          >
            {filter.isValid ? "Valid Filter" : "Filter (with warnings)"}
          </span>
          {filter.fieldsUsed.length > 0 && (
            <span className="text-xs text-gray-400 ml-2">
              {filter.fieldsUsed.length} field
              {filter.fieldsUsed.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-pcdc-blue transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>

      {/* JSON body */}
      <pre className="json-display p-3 text-xs leading-relaxed overflow-x-auto bg-gray-900 text-green-300 max-h-80 overflow-y-auto">
        {jsonStr}
      </pre>

      {/* Errors / warnings */}
      {filter.errors.length > 0 && (
        <div className="px-3 py-2 bg-red-50 border-t border-red-200">
          {filter.errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600">
              ⛔ {err}
            </p>
          ))}
        </div>
      )}
      {filter.warnings.length > 0 && (
        <div className="px-3 py-2 bg-amber-50 border-t border-amber-200">
          {filter.warnings.map((w, i) => (
            <p key={i} className="text-xs text-amber-600">
              ⚠️ {w}
            </p>
          ))}
        </div>
      )}

      {/* Fields used chips */}
      {filter.fieldsUsed.length > 0 && (
        <div className="px-3 py-2 bg-gray-50 border-t border-gray-200 flex flex-wrap gap-1">
          {filter.fieldsUsed.map((f) => (
            <span
              key={f}
              className="px-2 py-0.5 text-[10px] bg-pcdc-blue/10 text-pcdc-blue rounded-full font-medium"
            >
              {f}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
