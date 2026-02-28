import { useState, useRef, useEffect } from "react";
import { Send, Square } from "lucide-react";

interface Props {
  onSend: (text: string) => void;
  onCancel: () => void;
  isLoading: boolean;
}

export default function InputBar({ onSend, onCancel, isLoading }: Props) {
  const [text, setText] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Listen for suggestion clicks from the empty state
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (typeof detail === "string") {
        onSend(detail);
      }
    };
    window.addEventListener("chatbot:suggest", handler);
    return () => window.removeEventListener("chatbot:suggest", handler);
  }, [onSend]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [isLoading]);

  const handleSubmit = () => {
    if (!text.trim() || isLoading) return;
    onSend(text.trim());
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const canSend = text.trim().length > 0 && !isLoading;

  return (
    <div className="px-4 py-3 bg-white border-t border-slate-200">
      <div className="max-w-3xl mx-auto">
        <div
          className={`flex items-end gap-2 rounded-2xl px-4 py-2.5 transition-all ${
            isLoading
              ? "bg-gray-50 border border-gray-200"
              : "bg-white border border-gray-300 hover:border-slate-400 focus-within:border-slate-500"
          }`}
          style={{ boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}
        >
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe the patient cohort you're looking for..."
            disabled={isLoading}
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-gray-700
                       focus:outline-none disabled:text-gray-400
                       placeholder:text-gray-400 max-h-32 leading-relaxed"
            style={{ minHeight: "28px" }}
            onInput={(e) => {
              const t = e.target as HTMLTextAreaElement;
              t.style.height = "auto";
              t.style.height = Math.min(t.scrollHeight, 128) + "px";
            }}
          />

          {isLoading ? (
            <button
              onClick={onCancel}
              className="flex-shrink-0 w-8 h-8 rounded-md bg-red-600 text-white
                         flex items-center justify-center hover:bg-red-700 transition-colors"
              title="Cancel"
            >
              <Square className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={!canSend}
              title="Send"
              className={`flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all ${
                canSend
                  ? "text-white bg-slate-900 hover:bg-slate-800"
                  : "bg-gray-100 text-gray-300 cursor-not-allowed"
              }`}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <p className="text-center text-[10px] text-gray-400 mt-1.5">
          Press Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
