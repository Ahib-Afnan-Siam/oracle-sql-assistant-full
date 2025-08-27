// src/components/ChatContext.tsx
import React, { createContext, useContext, useRef, useState, ReactNode } from "react";

type TableData = (string | number | null)[][];

type OracleError = {
  code?: string;
  error?: string;
  message?: string;
  sql?: string;
  missing_tables?: string[];
  valid_columns?: string[];
  validation_details?: any;
  suggestion?: string;
  suggestions?: string[]; // ← added to match backend and ChatPanel
};

type Message = {
  sender: "user" | "bot";
  content: string | TableData | OracleError;
  id: string;
  type: "user" | "status" | "summary" | "table" | "error";
};

type LastIds = { turn_id?: number; sql_sample_id?: number | null; summary_sample_id?: number | null };

interface ChatContextType {
  messages: Message[];
  addMessage: (message: Message) => string;
  updateMessage: (
    id: string,
    content: string | TableData | OracleError,
    overrides?: Partial<Message>
  ) => void;
  clearMessages: () => void;
  processMessage: (userMessage: string, selectedDB: string) => void;
  isTyping: boolean;
  isPaused: boolean;
  setIsPaused: (val: boolean) => void; // pressing Stop -> setIsPaused(true) aborts the request
  selectedDB: string;
  setSelectedDB: (db: string) => void;
  lastIds: LastIds; // retains API compatibility; now populated from non-stream payload.ids
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isPaused, _setIsPaused] = useState(false);
  const [selectedDB, setSelectedDB] = useState("source_db_1");
  const [lastIds, setLastIds] = useState<LastIds>({});

  const abortControllerRef = useRef<AbortController | null>(null);
  const thinkingMsgIdRef = useRef<string | null>(null);

  const generateId = () =>
    `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const addMessage = (message: Message) => {
    const newMessage = { ...message, id: message.id || generateId() };
    setMessages((prev) => [...prev, newMessage]);
    return newMessage.id;
  };

  const updateMessage = (
    id: string,
    content: string | TableData | OracleError,
    overrides?: Partial<Message>
  ) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...overrides, content } : m))
    );
  };

  const clearMessages = () => {
    setMessages([]);
    setLastIds({});
  };

  const setIsPausedAndAbort = (val: boolean) => {
    _setIsPaused(val);
    if (val && abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const processMessage = async (userMessage: string, selectedDB: string) => {
    const q = userMessage.trim();
    if (!q || isTyping) return;

    // reset any previous pause and create a fresh controller
    setIsPausedAndAbort(false);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLastIds({});
    setIsTyping(true);

    addMessage({ sender: "user", content: q, id: generateId(), type: "user" });
    const thinkingId = addMessage({
      sender: "bot",
      content: "Thinking...",
      id: generateId(),
      type: "status",
    });
    thinkingMsgIdRef.current = thinkingId;

    try {
      const res = await fetch("http://127.0.0.1:8090/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, selected_db: selectedDB }),
        signal: controller.signal,
      });

      const payload = await res.json();
      if (!res.ok) {
        const text = typeof payload === "string" ? payload : payload?.detail || res.statusText;
        updateMessage(thinkingId, { error: "HTTPError", message: text } as any, { type: "error" });
        setIsTyping(false);
        return;
      }

      // handle backend error envelope
      if (payload?.status === "error" || (payload?.message && !payload?.results)) {
        updateMessage(
          thinkingId,
          {
            error: payload.error,            // may be undefined
            message: payload.message ?? "Request failed.",
            sql: payload.sql,
            valid_columns: payload.valid_columns,
            missing_tables: payload.missing_tables,
            suggestions: payload.suggestions,
          } as any,
          { type: "error" }
        );
        setIsTyping(false);
        return;
      }

      // ✅ keep FeedbackBox IDs flowing in non-stream mode
      if (payload?.ids || payload?.turn_id) {
        setLastIds((prev) => ({
          ...prev,
          ...(payload.ids ?? {}),
          ...(payload.turn_id ? { turn_id: payload.turn_id } : {}),
          ...(payload.sql_sample_id ? { sql_sample_id: payload.sql_sample_id } : {}),
          ...(payload.summary_sample_id ? { summary_sample_id: payload.summary_sample_id } : {}),
        }));
      }

      if (payload?.error) {
        // normalize into a consistent object
        const msg: string =
          typeof payload.error === "string" ? payload.error : (payload.error?.message || "Request failed.");
        const codeMatch = msg.match(/ORA-\d{5}/)?.[0];
        updateMessage(
          thinkingId,
          {
            error: codeMatch || "OracleError",
            message: msg,
            sql: payload.sql,
            valid_columns: payload.valid_columns,
            missing_tables: payload.missing_tables,
            suggestions: payload.suggestions,
          } as any,
          { type: "error" }
        );
        setIsTyping(false);
        return;
      }

      const mode: string = payload?.display_mode || "table";

      // 🫧 Prefer morphing the "Thinking..." bubble into the summary if present
      let usedThinkingBubble = false;
      if ((mode === "summary" || mode === "both") && payload?.summary) {
        updateMessage(thinkingId, payload.summary as string, { type: "summary" });
        usedThinkingBubble = true;
      }

      // Table message (separate bubble) — add status === "success" guard
      if (
        payload?.status === "success" &&
        (mode === "table" || mode === "both") &&
        payload?.results?.columns
      ) {
        const columns: string[] = payload.results.columns || [];
        const rows: any[][] = payload.results.rows || [];
        if (columns.length) {
          addMessage({
            sender: "bot",
            content: [columns, ...(rows || [])],
            id: generateId(),
            type: "table",
          });
        }
      }

      // If we didn't repurpose the thinking bubble, remove it to avoid a stray status line
      if (!usedThinkingBubble) {
        setMessages((prev) => prev.filter((m) => m.id !== thinkingId));
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        // user pressed Stop → show stopped on the same bubble
        if (thinkingMsgIdRef.current) {
          updateMessage(thinkingMsgIdRef.current, "⏹️ Stopped.", { type: "status" });
        } else {
          addMessage({
            sender: "bot",
            content: "⏹️ Stopped.",
            type: "status",
            id: generateId(),
          });
        }
      } else {
        // transform the status bubble into an error bubble
        if (thinkingMsgIdRef.current) {
          updateMessage(thinkingMsgIdRef.current, "⚠️ Error during processing.", { type: "error" });
        } else {
          addMessage({ sender: "bot", content: "⚠️ Error during processing.", type: "error", id: generateId() });
        }
      }
    } finally {
      setIsTyping(false);
      abortControllerRef.current = null;
      thinkingMsgIdRef.current = null;
      _setIsPaused(false);
    }
  };

  return (
    <ChatContext.Provider
      value={{
        messages,
        addMessage,
        updateMessage,
        clearMessages,
        processMessage,
        isTyping,
        isPaused,
        setIsPaused: setIsPausedAndAbort,
        selectedDB,
        setSelectedDB,
        lastIds,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = (): ChatContextType => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
};
