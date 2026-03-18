import { useState, useRef, useEffect } from "react";
import {
  Download,
  Copy,
  Check,
  FileCode2,
  BarChart3,
  FileJson,
  ChevronDown,
} from "lucide-react";
import { exportAsGraphQL, exportAsAggregation } from "../api";

interface Props {
  filter: Record<string, unknown>;
}

type CopyState = "idle" | "copied-gql" | "copied-agg" | "copied-json";

export default function ExportMenu({ filter }: Props) {
  const [open, setOpen] = useState(false);
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const menuRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const resetCopy = () => setTimeout(() => setCopyState("idle"), 2000);

  const handleCopyJSON = async () => {
    await navigator.clipboard.writeText(JSON.stringify(filter, null, 2));
    setCopyState("copied-json");
    resetCopy();
  };

  const handleCopyGraphQL = async () => {
    try {
      const gql = await exportAsGraphQL(filter);
      await navigator.clipboard.writeText(gql);
      setCopyState("copied-gql");
    } catch {
      // Fallback: build locally
      const gql = `query {\n  subject(filter: ${JSON.stringify(filter, null, 2)}, accessibility: accessible) {\n    subject_id\n  }\n}`;
      await navigator.clipboard.writeText(gql);
      setCopyState("copied-gql");
    }
    resetCopy();
  };

  const handleCopyAggregation = async () => {
    try {
      const agg = await exportAsAggregation(filter);
      await navigator.clipboard.writeText(agg);
      setCopyState("copied-agg");
    } catch {
      const agg = `query {\n  _aggregation(filter: ${JSON.stringify(filter, null, 2)}, accessibility: accessible) {\n    _totalCount\n  }\n}`;
      await navigator.clipboard.writeText(agg);
      setCopyState("copied-agg");
    }
    resetCopy();
  };

  const handleDownloadJSON = () => {
    const blob = new Blob([JSON.stringify(filter, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "pcdc-filter.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-slate-900
                   hover:bg-white px-2 py-1 rounded-md transition-colors"
      >
        {copyState !== "idle" ? (
          <>
            <Check className="w-3 h-3 text-green-600" /> Copied!
          </>
        ) : (
          <>
            <Download className="w-3 h-3" />
            Export
            <ChevronDown className="w-2.5 h-2.5" />
          </>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-1 w-52 bg-white rounded-lg border border-gray-200
                     shadow-lg z-50 py-1 overflow-hidden"
        >
          <button
            onClick={() => { handleCopyJSON(); setOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gray-700
                       hover:bg-slate-50 transition-colors text-left"
          >
            <Copy className="w-3.5 h-3.5 text-gray-400" />
            <div>
              <p className="font-medium">Copy Filter JSON</p>
              <p className="text-[10px] text-gray-400">Raw Guppy filter object</p>
            </div>
          </button>

          <button
            onClick={() => { handleCopyGraphQL(); setOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gray-700
                       hover:bg-slate-50 transition-colors text-left"
          >
            <FileCode2 className="w-3.5 h-3.5 text-gray-400" />
            <div>
              <p className="font-medium">Copy as GraphQL Query</p>
              <p className="text-[10px] text-gray-400">Full query with filter embedded</p>
            </div>
          </button>

          <button
            onClick={() => { handleCopyAggregation(); setOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gray-700
                       hover:bg-slate-50 transition-colors text-left"
          >
            <BarChart3 className="w-3.5 h-3.5 text-gray-400" />
            <div>
              <p className="font-medium">Copy as Aggregation</p>
              <p className="text-[10px] text-gray-400">_totalCount query with filter</p>
            </div>
          </button>

          <div className="border-t border-gray-100 my-1" />

          <button
            onClick={() => { handleDownloadJSON(); setOpen(false); }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-gray-700
                       hover:bg-slate-50 transition-colors text-left"
          >
            <FileJson className="w-3.5 h-3.5 text-gray-400" />
            <div>
              <p className="font-medium">Download .json File</p>
              <p className="text-[10px] text-gray-400">Save filter to disk</p>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}
