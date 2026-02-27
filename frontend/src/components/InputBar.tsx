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

  // Auto-focus
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

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="max-w-3xl mx-auto flex items-end gap-2">
        <textarea
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe the patient cohort you're looking for..."
          disabled={isLoading}
          rows={1}
          className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm
                     focus:outline-none focus:border-pcdc-teal focus:ring-1 focus:ring-pcdc-teal/30
                     disabled:bg-gray-50 disabled:text-gray-400
                     placeholder:text-gray-400 max-h-32"
          style={{
            height: "auto",
            minHeight: "42px",
          }}
          onInput={(e) => {
            const target = e.target as HTMLTextAreaElement;
            target.style.height = "auto";
            target.style.height = Math.min(target.scrollHeight, 128) + "px";
          }}
        />
        {isLoading ? (
          <button
            onClick={onCancel}
            className="flex-shrink-0 w-10 h-10 rounded-xl bg-red-500 text-white
                       flex items-center justify-center hover:bg-red-600 transition-colors"
            title="Cancel"
          >
            <Square className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim()}
            className="flex-shrink-0 w-10 h-10 rounded-xl bg-pcdc-teal text-white
                       flex items-center justify-center hover:bg-pcdc-teal/90 transition-colors
                       disabled:opacity-40 disabled:cursor-not-allowed"
            title="Send"
          >
            <Send className="w-4 h-4" />
          </button>
        )}
      </div>
      <p className="text-[10px] text-gray-400 text-center mt-1.5">
        Press Enter to send · Shift+Enter for new line
      </p>
    </div>
  );
}
