/**
 * SSE-based API client for the PCDC chatbot backend.
 */

import type { SavedFilter } from "./types";

const API_BASE = "/chat";

export interface ChatRequestBody {
  message: string;
  conversation_id?: string;
  history?: { role: string; content: string }[];
}

export type SSECallback = (event: string, data: unknown) => void;

/**
 * Send a chat message and listen to the SSE stream.
 * Returns an AbortController to cancel the request.
 */
export function sendChatMessage(
  body: ChatRequestBody,
  onEvent: SSECallback
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!response.ok) {
        onEvent("error", { text: `HTTP ${response.status}` });
        onEvent("done", {});
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        onEvent("error", { text: "No response body" });
        onEvent("done", {});
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE lines
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let currentEvent = "message";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const raw = line.slice(6);
            try {
              const data = JSON.parse(raw);
              onEvent(currentEvent, data);
            } catch {
              onEvent(currentEvent, raw);
            }
          }
          // Empty line resets event name
          if (line === "") {
            currentEvent = "message";
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      onEvent("error", { text: String(err) });
      onEvent("done", {});
    }
  })();

  return controller;
}


// ── Saved Filters API (F1) ──────────────────────────────────────

export async function saveFilter(body: {
  name: string;
  filter_json: Record<string, unknown>;
  nl_description?: string;
  conversation_id?: string;
}): Promise<SavedFilter> {
  const res = await fetch("/filters/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Save failed: ${res.status}`);
  return res.json();
}

export async function listFilters(): Promise<SavedFilter[]> {
  const res = await fetch("/filters");
  if (!res.ok) throw new Error(`List failed: ${res.status}`);
  const data = await res.json();
  return data.filters;
}

export async function deleteFilter(id: string): Promise<void> {
  const res = await fetch(`/filters/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Delete failed: ${res.status}`);
}


// ── Export API (F3) ─────────────────────────────────────────────

export async function exportAsGraphQL(
  filter: Record<string, unknown>
): Promise<string> {
  const res = await fetch("/filters/export/graphql", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filter }),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const data = await res.json();
  return data.graphql;
}

export async function exportAsAggregation(
  filter: Record<string, unknown>
): Promise<string> {
  const res = await fetch("/filters/export/aggregation", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filter }),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const data = await res.json();
  return data.graphql;
}
