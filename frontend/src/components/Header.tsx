import { Microscope, Trash2 } from "lucide-react";

interface Props {
  onClear: () => void;
  messageCount: number;
}

export default function Header({ onClear, messageCount }: Props) {
  return (
    <header className="bg-pcdc-blue text-white px-6 py-3 flex items-center justify-between shadow-md">
      <div className="flex items-center gap-3">
        <Microscope className="w-7 h-7 text-pcdc-light" />
        <div>
          <h1 className="text-lg font-semibold leading-tight">
            Cohort Discovery Chatbot
          </h1>
          <p className="text-xs text-pcdc-light/80">
            Generate Guppy GraphQL filters with natural language
          </p>
        </div>
      </div>
      {messageCount > 0 && (
        <button
          onClick={onClear}
          title="Clear conversation"
          className="flex items-center gap-1.5 text-sm text-pcdc-light/70 hover:text-white transition-colors px-2 py-1 rounded hover:bg-white/10"
        >
          <Trash2 className="w-4 h-4" />
          Clear
        </button>
      )}
    </header>
  );
}
