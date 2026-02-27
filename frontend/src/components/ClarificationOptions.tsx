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
    <div className="mt-3 flex flex-wrap gap-2">
      {options.map((opt, i) => (
        <button
          key={i}
          disabled={disabled}
          onClick={() => onSelect(opt)}
          className="px-3 py-1.5 text-sm rounded-full border border-pcdc-teal text-pcdc-teal
                     hover:bg-pcdc-teal hover:text-white transition-colors
                     disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
