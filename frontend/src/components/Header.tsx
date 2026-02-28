import { Microscope, Trash2 } from "lucide-react";

interface Props {
  onClear: () => void;
  messageCount: number;
}

export default function Header({ onClear, messageCount }: Props) {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3.5 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center">
          <Microscope className="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 className="text-base font-semibold text-slate-900 leading-tight tracking-tight">
            PCDC Cohort Discovery
          </h1>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Natural language → Guppy GraphQL filters
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {messageCount > 0 && (
          <button
            onClick={onClear}
            title="Clear conversation"
            className="flex items-center gap-1.5 text-xs text-slate-600 hover:text-slate-900 transition-colors px-3 py-1.5 rounded-md hover:bg-slate-100 border border-transparent"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
      </div>
    </header>
  );
}
