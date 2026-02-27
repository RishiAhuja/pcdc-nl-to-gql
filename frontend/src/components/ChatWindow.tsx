import { useRef, useEffect } from "react";
import type { ChatMessage, ClarificationOption } from "../types";
import MessageBubble from "./MessageBubble";
import { Microscope } from "lucide-react";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  onClarificationSelect: (option: ClarificationOption) => void;
}

const SUGGESTIONS = [
  "Show me all AML patients under 5",
  "Find relapsed neuroblastoma cases",
  "Patients with WBC count above 50",
  "Male patients with Down syndrome",
];

export default function ChatWindow({
  messages,
  isLoading,
  onClarificationSelect,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
        <div className="w-16 h-16 rounded-full bg-pcdc-teal/10 flex items-center justify-center mb-4">
          <Microscope className="w-8 h-8 text-pcdc-teal" />
        </div>
        <h2 className="text-xl font-semibold text-gray-800 mb-2">
          Ask me about cohort data
        </h2>
        <p className="text-sm text-gray-500 max-w-md mb-6">
          Describe the patient cohort you&#39;re looking for in plain English
          and I&#39;ll generate a Guppy-compatible GraphQL filter for you.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-600
                         hover:border-pcdc-teal hover:text-pcdc-teal transition-colors"
              // We bubble this up via a custom event since we don't have sendMessage here
              onClick={() => {
                window.dispatchEvent(
                  new CustomEvent("chatbot:suggest", { detail: s })
                );
              }}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 custom-scrollbar">
      {messages.map((msg) => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onClarificationSelect={onClarificationSelect}
          isStreaming={isLoading}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
