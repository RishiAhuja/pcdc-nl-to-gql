/* ── Shared types for the PCDC chatbot frontend ─────────── */

export type MessageRole = "user" | "assistant" | "system";

export interface ClarificationOption {
  label: string;
  value: string;
}

export interface FilterResult {
  filter: Record<string, unknown>;
  isValid: boolean;
  errors: string[];
  warnings: string[];
  fieldsUsed: string[];
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;

  /** Set when the message includes a generated filter */
  filter?: FilterResult;

  /** Set when the assistant asks for clarification */
  clarification?: {
    question: string;
    options: ClarificationOption[];
  };

  /** True while the assistant is still generating */
  isLoading?: boolean;

  /** Current status text while processing */
  statusText?: string;
}

export type SSEEventType =
  | "token"
  | "filter_json"
  | "clarification"
  | "error"
  | "done"
  | "status";
