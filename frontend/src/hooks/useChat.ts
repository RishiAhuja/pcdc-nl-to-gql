import { useState, useCallback, useRef } from "react";
import type { ChatMessage, FilterResult, ClarificationOption } from "../types";
import { sendChatMessage } from "../api";

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId] = useState(() => genId());
  const abortRef = useRef<AbortController | null>(null);

  // Append or update messages
  const appendMsg = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const updateLastAssistant = useCallback(
    (updater: (prev: ChatMessage) => ChatMessage) => {
      setMessages((prev) => {
        const idx = prev.length - 1;
        if (idx < 0 || prev[idx].role !== "assistant") return prev;
        const copy = [...prev];
        copy[idx] = updater(copy[idx]);
        return copy;
      });
    },
    []
  );

  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim() || isLoading) return;

      // Add user message
      const userMsg: ChatMessage = {
        id: genId(),
        role: "user",
        content: text,
        timestamp: new Date(),
      };
      appendMsg(userMsg);

      // Add placeholder assistant message
      const assistantId = genId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        isLoading: true,
      };
      appendMsg(assistantMsg);

      setIsLoading(true);

      const history = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const controller = sendChatMessage(
        {
          message: text,
          conversation_id: conversationId,
          history: [...history, { role: "user", content: text }],
        },
        (event, data) => {
          switch (event) {
            case "status":
              updateLastAssistant((prev) => ({
                ...prev,
                statusText: (data as { text?: string }).text,
              }));
              break;

            case "token":
              updateLastAssistant((prev) => ({
                ...prev,
                content:
                  prev.content + ((data as { text?: string }).text || ""),
              }));
              break;

            case "filter_json": {
              const payload = data as {
                filter: Record<string, unknown>;
                is_valid: boolean;
                errors: string[];
                warnings: string[];
                fields_used: string[];
              };
              const filterResult: FilterResult = {
                filter: payload.filter,
                isValid: payload.is_valid,
                errors: payload.errors || [],
                warnings: payload.warnings || [],
                fieldsUsed: payload.fields_used || [],
              };
              updateLastAssistant((prev) => ({
                ...prev,
                filter: filterResult,
              }));
              break;
            }

            case "clarification": {
              const payload = data as {
                question: string;
                options: ClarificationOption[];
              };
              updateLastAssistant((prev) => ({
                ...prev,
                content: payload.question,
                clarification: {
                  question: payload.question,
                  options: payload.options,
                },
              }));
              break;
            }

            case "error":
              updateLastAssistant((prev) => ({
                ...prev,
                content:
                  prev.content +
                  "\n\n⚠️ " +
                  ((data as { text?: string }).text || "Unknown error"),
                isLoading: false,
              }));
              break;

            case "done":
              updateLastAssistant((prev) => ({
                ...prev,
                isLoading: false,
                statusText: undefined,
              }));
              setIsLoading(false);
              break;
          }
        }
      );

      abortRef.current = controller;
    },
    [
      messages,
      isLoading,
      conversationId,
      appendMsg,
      updateLastAssistant,
    ]
  );

  const selectClarification = useCallback(
    (option: ClarificationOption) => {
      sendMessage(option.label);
    },
    [sendMessage]
  );

  const cancelRequest = useCallback(() => {
    abortRef.current?.abort();
    setIsLoading(false);
    updateLastAssistant((prev) => ({
      ...prev,
      isLoading: false,
      statusText: undefined,
    }));
  }, [updateLastAssistant]);

  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  return {
    messages,
    isLoading,
    sendMessage,
    selectClarification,
    cancelRequest,
    clearMessages,
    conversationId,
  };
}
