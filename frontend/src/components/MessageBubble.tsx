import { Bot, User } from "lucide-react";
import type { ChatMessage, ClarificationOption } from "../types";
import FilterDisplay from "./FilterDisplay";
import ClarificationOptions from "./ClarificationOptions";

interface Props {
  message: ChatMessage;
  onClarificationSelect: (option: ClarificationOption) => void;
  isStreaming: boolean;
}

export default function MessageBubble({
  message,
  onClarificationSelect,
  isStreaming,
}: Props) {
  const isUser = message.role === "user";

  return (
    <div
      className={`message-enter flex gap-3 ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser ? "bg-pcdc-blue" : "bg-pcdc-teal"
        }`}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div
        className={`max-w-[75%] ${isUser ? "text-right" : "text-left"}`}
      >
        <div
          className={`inline-block px-4 py-2.5 rounded-2xl ${
            isUser
              ? "bg-pcdc-blue text-white rounded-br-md"
              : "bg-white border border-gray-200 text-gray-800 rounded-bl-md shadow-sm"
          }`}
        >
          {/* Status indicator */}
          {message.isLoading && message.statusText && (
            <div className="text-xs text-pcdc-teal mb-1.5 flex items-center gap-1.5">
              <span className="thinking-dot" />
              <span className="thinking-dot" style={{ animationDelay: "0.2s" }} />
              <span className="thinking-dot" style={{ animationDelay: "0.4s" }} />
              <span className="ml-1 italic">{message.statusText}</span>
            </div>
          )}

          {/* Message text */}
          {message.content ? (
            <div className="text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </div>
          ) : message.isLoading ? (
            <div className="flex items-center gap-1.5 py-1">
              <span className="thinking-dot" />
              <span className="thinking-dot" style={{ animationDelay: "0.2s" }} />
              <span className="thinking-dot" style={{ animationDelay: "0.4s" }} />
            </div>
          ) : null}
        </div>

        {/* Filter result (rendered outside bubble for full width) */}
        {message.filter && <FilterDisplay filter={message.filter} />}

        {/* Clarification options */}
        {message.clarification && (
          <ClarificationOptions
            options={message.clarification.options}
            onSelect={onClarificationSelect}
            disabled={isStreaming}
          />
        )}
      </div>
    </div>
  );
}
