import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
        className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center shadow-message ring-1 ${
          isUser
            ? "ring-slate-300"
            : "ring-slate-200"
        }`}
        style={{
          background: isUser
            ? "#0f172a"
            : "#1f2937",
        }}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className={`max-w-[78%] ${ isUser ? "items-end" : "items-start" } flex flex-col`}>
        {/* Role label */}
        <span className={`text-[10px] font-medium mb-1 px-1 ${
          isUser ? "text-right text-slate-500" : "text-slate-500"
        }`}>
          {isUser ? "Researcher" : "PCDC Assistant"}
        </span>

        <div
          className={`px-4 py-3 rounded-2xl text-sm leading-relaxed ${
            isUser
              ? "text-white rounded-tr-sm shadow-message"
              : "bg-white border border-gray-200 text-gray-800 rounded-tl-sm shadow-message"
          }`}
          style={isUser ? {
            background: "#0f172a",
          } : { borderLeft: "3px solid #cbd5e1" }}
        >
          {/* Status indicator */}
          {message.isLoading && message.statusText && (
            <div className="flex items-center gap-2 mb-2">
              <span className="thinking-dot text-slate-600" />
              <span className="thinking-dot text-slate-600" />
              <span className="thinking-dot text-slate-600" />
              <span className="ml-1 text-xs shimmer-text font-medium">{message.statusText}</span>
            </div>
          )}

          {/* Message text */}
          {message.content ? (
            isUser ? (
              <div className="whitespace-pre-wrap">{message.content}</div>
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                  strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                  em: ({ children }) => <em className="italic">{children}</em>,
                  ul: ({ children }) => <ul className="list-disc list-inside space-y-0.5 my-1.5 ml-1">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside space-y-0.5 my-1.5 ml-1">{children}</ol>,
                  li: ({ children }) => <li className="text-gray-800">{children}</li>,
                  code: ({ children }) => <code className="bg-slate-100 text-slate-800 px-1 py-0.5 rounded text-xs font-mono">{children}</code>,
                  pre: ({ children }) => <pre className="bg-slate-100 rounded p-2 my-2 overflow-x-auto text-xs font-mono">{children}</pre>,
                  h1: ({ children }) => <h1 className="text-base font-bold text-gray-900 mb-1 mt-2">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-sm font-bold text-gray-900 mb-1 mt-2">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-900 mb-0.5 mt-1.5">{children}</h3>,
                  blockquote: ({ children }) => <blockquote className="border-l-2 border-slate-300 pl-3 my-1.5 text-slate-600 italic">{children}</blockquote>,
                  a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline hover:text-blue-800">{children}</a>,
                  hr: () => <hr className="border-slate-200 my-2" />,
                }}
              >
                {message.content}
              </ReactMarkdown>
            )
          ) : message.isLoading ? (
            <div className="flex items-center gap-1.5 py-0.5 text-slate-600">
              <span className="thinking-dot" />
              <span className="thinking-dot" />
              <span className="thinking-dot" />
            </div>
          ) : null}
        </div>

        {/* Filter result */}
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
