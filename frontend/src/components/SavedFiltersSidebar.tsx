import { useState, useEffect } from "react";
import {
  Bookmark,
  Trash2,
  Copy,
  Check,
  X,
  ChevronRight,
  FolderOpen,
} from "lucide-react";
import { listFilters, deleteFilter } from "../api";
import type { SavedFilter } from "../types";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onLoadFilter: (filter: SavedFilter) => void;
}

export default function SavedFiltersSidebar({
  isOpen,
  onClose,
  onLoadFilter,
}: Props) {
  const [filters, setFilters] = useState<SavedFilter[]>([]);
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const fetchFilters = async () => {
    setLoading(true);
    try {
      const data = await listFilters();
      setFilters(data);
    } catch (err) {
      console.error("Failed to load filters:", err);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (isOpen) fetchFilters();
  }, [isOpen]);

  const handleDelete = async (id: string) => {
    try {
      await deleteFilter(id);
      setFilters((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      console.error("Failed to delete filter:", err);
    }
  };

  const handleCopy = async (filter: SavedFilter) => {
    await navigator.clipboard.writeText(
      JSON.stringify(filter.filter_json, null, 2)
    );
    setCopiedId(filter.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative ml-auto w-80 h-full bg-white border-l border-gray-200 shadow-xl
                      flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <Bookmark className="w-4 h-4 text-slate-700" />
            <h2 className="text-sm font-semibold text-slate-900">
              Saved Filters
            </h2>
            <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-full font-medium">
              {filters.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {loading ? (
            <div className="px-4 py-8 text-center text-xs text-gray-400">
              Loading...
            </div>
          ) : filters.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <FolderOpen className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-xs text-gray-400">No saved filters yet</p>
              <p className="text-[10px] text-gray-300 mt-1">
                Generate a filter and click "Save" to add it here
              </p>
            </div>
          ) : (
            <div className="py-2">
              {filters.map((f) => (
                <div
                  key={f.id}
                  className="px-3 py-2.5 mx-2 mb-1 rounded-lg hover:bg-slate-50
                             transition-colors group cursor-pointer border border-transparent
                             hover:border-gray-200"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div
                      className="flex-1 min-w-0"
                      onClick={() => onLoadFilter(f)}
                    >
                      <p className="text-xs font-medium text-slate-800 truncate">
                        {f.name}
                      </p>
                      {f.nl_description && (
                        <p className="text-[10px] text-gray-400 mt-0.5 line-clamp-2">
                          {f.nl_description}
                        </p>
                      )}
                      <div className="flex items-center gap-1.5 mt-1.5">
                        <span className="text-[9px] text-gray-400">
                          {new Date(f.created_at).toLocaleDateString()}
                        </span>
                        {f.fields_used.length > 0 && (
                          <span className="text-[9px] text-gray-300">
                            · {f.fields_used.length} field
                            {f.fields_used.length !== 1 ? "s" : ""}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCopy(f);
                        }}
                        className="p-1 text-gray-400 hover:text-slate-700 rounded"
                        title="Copy JSON"
                      >
                        {copiedId === f.id ? (
                          <Check className="w-3 h-3 text-green-600" />
                        ) : (
                          <Copy className="w-3 h-3" />
                        )}
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(f.id);
                        }}
                        className="p-1 text-gray-400 hover:text-red-500 rounded"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                      <ChevronRight className="w-3 h-3 text-gray-300" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
