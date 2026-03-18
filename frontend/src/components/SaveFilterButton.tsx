import { useState } from "react";
import { Bookmark, Check, X } from "lucide-react";
import { saveFilter } from "../api";

interface Props {
  filter: Record<string, unknown>;
  explanation?: string;
  conversationId?: string;
}

export default function SaveFilterButton({
  filter,
  explanation,
  conversationId,
}: Props) {
  const [mode, setMode] = useState<"idle" | "naming" | "saved">("idle");
  const [name, setName] = useState("");

  const handleSave = async () => {
    if (!name.trim()) return;
    try {
      await saveFilter({
        name: name.trim(),
        filter_json: filter,
        nl_description: explanation || "",
        conversation_id: conversationId,
      });
      setMode("saved");
      setTimeout(() => setMode("idle"), 2500);
    } catch (err) {
      console.error("Failed to save filter:", err);
      setMode("idle");
    }
  };

  if (mode === "saved") {
    return (
      <span className="flex items-center gap-1 text-xs text-green-600 px-2 py-1">
        <Check className="w-3 h-3" /> Saved!
      </span>
    );
  }

  if (mode === "naming") {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="Filter name..."
          className="text-xs px-2 py-1 border border-gray-300 rounded-md focus:outline-none
                     focus:border-slate-500 w-36"
          autoFocus
        />
        <button
          onClick={handleSave}
          disabled={!name.trim()}
          className="text-xs px-2 py-1 bg-slate-900 text-white rounded-md
                     hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save
        </button>
        <button
          onClick={() => { setMode("idle"); setName(""); }}
          className="text-gray-400 hover:text-gray-600"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setMode("naming")}
      className="flex items-center gap-1 text-xs text-gray-500
                 hover:text-slate-900 hover:bg-white px-2 py-1 rounded-md transition-colors"
      title="Save this filter"
    >
      <Bookmark className="w-3 h-3" />
      Save
    </button>
  );
}
