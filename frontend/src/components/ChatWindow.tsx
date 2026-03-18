import { useRef, useEffect } from "react";
import type { ChatMessage, ClarificationOption } from "../types";
import MessageBubble from "./MessageBubble";
import { Microscope, Search, ShieldCheck, History, FileText, ArrowLeftRight, BookOpen } from "lucide-react";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  onClarificationSelect: (option: ClarificationOption) => void;
}

const SUGGESTIONS = [
  { text: "Show all AML patients under age 5" },
  { text: "Find relapsed neuroblastoma cases" },
  { text: "Patients with WBC count above 50" },
  { text: "Female patients with Down syndrome" },
];

const TEMPLATES = [
  {
    icon: Search,
    category: "Filter",
    examples: [
      "All ___ patients who are ___",
      "Patients diagnosed between ___ and ___",
    ],
  },
  {
    icon: BookOpen,
    category: "Documentation",
    examples: [
      "What fields describe disease staging?",
      "Explain the treatment response values",
    ],
  },
  {
    icon: ArrowLeftRight,
    category: "Compare",
    examples: [
      "Compare my last two filters",
      "How does this cohort differ from the previous one?",
    ],
  },
  {
    icon: FileText,
    category: "Explain",
    examples: [
      "Paste a filter JSON to get a plain-English explanation",
    ],
  },
];

const FEATURES = [
  {
    icon: Search,
    color: "bg-slate-50 text-slate-700 border-slate-200",
    title: "Smart Retrieval",
    desc: "Finds relevant schema fields automatically using semantic search",
  },
  {
    icon: ShieldCheck,
    color: "bg-slate-50 text-slate-700 border-slate-200",
    title: "Validated Output",
    desc: "Every filter is checked against the real PCDC schema before delivery",
  },
  {
    icon: History,
    color: "bg-slate-50 text-slate-700 border-slate-200",
    title: "Context-Aware",
    desc: "Follow-up queries build on prior conversation turns automatically",
  },
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
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto px-6 py-10 flex flex-col items-center">
          <div className="w-14 h-14 rounded-xl flex items-center justify-center mb-5 bg-slate-900 shadow-card">
            <Microscope className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-gray-800 mb-2 text-center tracking-tight">
            Describe the cohort you need
          </h2>
          <p className="text-sm text-gray-500 text-center max-w-sm mb-8 leading-relaxed">
            Describe patients in plain English. I'll generate a Guppy-compatible
            GraphQL filter you can use directly in the PCDC portal.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full mb-8">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className={`feature-card rounded-xl border p-4 bg-white shadow-message ${f.color.split(" ").slice(2).join(" ")}`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2.5 ${f.color.split(" ").slice(0,2).join(" ")}`}>
                  <f.icon className="w-4 h-4" />
                </div>
                <p className="text-xs font-semibold text-gray-700 mb-1">{f.title}</p>
                <p className="text-[11px] text-gray-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>

          <div className="w-full">
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Example prompts</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  className="group flex items-center px-4 py-3 rounded-lg bg-white border border-gray-200
                             hover:border-slate-400 hover:bg-slate-50 transition-all text-left shadow-message"
                  onClick={() => {
                    window.dispatchEvent(
                      new CustomEvent("chatbot:suggest", { detail: s.text })
                    );
                  }}
                >
                  <span className="text-sm text-gray-600 group-hover:text-slate-900 transition-colors leading-tight">
                    {s.text}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Query Templates (F4) */}
          <div className="w-full mt-6">
            <div className="mb-3">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Query Templates</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {TEMPLATES.map((t) => (
                <div
                  key={t.category}
                  className="rounded-lg border border-gray-200 bg-white p-3 shadow-message"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <t.icon className="w-3.5 h-3.5 text-slate-600" />
                    <span className="text-[11px] font-semibold text-slate-700 uppercase tracking-wide">
                      {t.category}
                    </span>
                  </div>
                  <div className="space-y-1">
                    {t.examples.map((ex) => (
                      <button
                        key={ex}
                        className="block w-full text-left text-xs text-gray-500 hover:text-slate-900 
                                   hover:bg-slate-50 px-2 py-1.5 rounded transition-colors"
                        onClick={() => {
                          window.dispatchEvent(
                            new CustomEvent("chatbot:suggest", { detail: ex })
                          );
                        }}
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5 custom-scrollbar">
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
