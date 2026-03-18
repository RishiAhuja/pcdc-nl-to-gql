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

export interface SavedFilter {
  id: string;
  name: string;
  filter_json: Record<string, unknown>;
  nl_description: string;
  fields_used: string[];
  created_at: string;
}

export interface FieldDiff {
  field: string;
  status: "added" | "removed" | "changed";
  value_a: unknown;
  value_b: unknown;
}

export interface ComparisonResult {
  diffs: FieldDiff[];
  summary: string;
  filter_a: Record<string, unknown>;
  filter_b: Record<string, unknown>;
  filter_a_name: string;
  filter_b_name: string;
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

  /** Set when the assistant returns a comparison */
  comparison?: ComparisonResult;

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
  | "status"
  | "comparison";
