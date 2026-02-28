import type { ClarificationOption } from "../types";

interface Props {
  options: ClarificationOption[];
  onSelect: (option: ClarificationOption) => void;
  disabled?: boolean;
}

export default function ClarificationOptions({
  options,
  onSelect,
  disabled,
}: Props) {
  return (
    <div className="mt-3">
      <p className="text-[10px] text-gray-400 uppercase tracking-wide font-medium mb-2 px-1">
        Choose one to continue
      </p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt, i) => (
          <button
            key={i}
            disabled={disabled}
            onClick={() => onSelect(opt)}
            className="px-4 py-2 text-sm rounded-md border border-slate-300 text-slate-700 bg-white
                       transition-colors font-medium hover:bg-slate-100 hover:border-slate-400
                       disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}
