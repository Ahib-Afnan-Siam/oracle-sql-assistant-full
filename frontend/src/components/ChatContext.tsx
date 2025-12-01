// src/components/ChatContext.tsx
import React, { createContext, useContext, useRef, useState, type ReactNode } from "react";

export type TableData = (string | number | null)[][];

export type OracleError = {
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

// Phase 4.2: Enhanced hybrid AI metadata structure
export type HybridMetadata = {
  processing_mode?: string;
  model_used?: string;
  selection_reasoning?: string;
  processing_time?: number;
  local_confidence?: number;
  api_confidence?: number;
};

export type Message = {
  sender: "user" | "bot";
  content: string | TableData | OracleError;
  id: string;
  type: "user" | "status" | "summary" | "table" | "error" | "file";
  // Phase 4.2: Add hybrid metadata to messages
  hybrid_metadata?: HybridMetadata;
  response_time?: number; // Track total response time from request to completion
  // File attachment properties
  file?: {
    name: string;
    size: number;
    type: string;
    content?: string; // base64 encoded content for images
  };
};

type LastIds = { turn_id?: number; sql_sample_id?: number | null; summary_sample_id?: number | null; chat_id?: number; message_id?: number };

// New Mode type - reordered to reflect preference
export type Mode = "General" | "PRAN ERP" | "RFL ERP" | "SOS";

interface ChatContextType {
  messages: Message[];
  addMessage: (message: Message) => string;
  updateMessage: (
    id: string,
    content: string | TableData | OracleError,
    overrides?: Partial<Message>
  ) => void;
  clearMessages: () => void;
  processMessage: (userMessage: string, selectedDB?: string, modeOverride?: Mode) => void;
  // Add file processing function
  processFileMessage: (file: File, userMessage: string, selectedDB?: string, modeOverride?: Mode) => void;
  isTyping: boolean;
  isPaused: boolean;
  setIsPaused: (val: boolean) => void; // pressing Stop -> setIsPaused(true) aborts the request
  selectedDB: string;
  setSelectedDB: (db: string) => void;
  mode: Mode;
  setMode: (mode: Mode) => void;
  lastIds: LastIds; // retains API compatibility; now populated from non-stream payload.ids
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isPaused, _setIsPaused] = useState(false);
  // Default DB changed to General mode (no DB)
  const [selectedDB, setSelectedDB] = useState<string>("");
  // 🔁 New default mode - changed to General
  const [mode, setMode] = useState<Mode>("General");
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

  // Helper to compute effective DB from Mode if caller didn't sync it
  const resolveDBFromMode = (m: Mode): string => {
    if (m === "SOS") return "source_db_1";
    if (m === "PRAN ERP") return "source_db_2";
    if (m === "RFL ERP") return "source_db_3";
    return ""; // General → no DB
    }

  const processMessage = async (
    userMessage: string,
    selectedDBArg?: string,
    modeOverride?: Mode
  ) => {
    const q = userMessage.trim();
    if (!q || isTyping) return;

    // Use override if provided, otherwise context mode
    const effectiveMode: Mode = modeOverride ?? mode;

    // If caller provided a DB, trust it; else infer from mode
    const effectiveDB: string =
      typeof selectedDBArg === "string" ? selectedDBArg : resolveDBFromMode(effectiveMode);

    // reset any previous pause and create a fresh controller
    setIsPausedAndAbort(false);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLastIds({});
    setIsTyping(true);

    // Phase 4.2: Track request start time for response time calculation
    const requestStartTime = Date.now();

    addMessage({ sender: "user", content: q, id: generateId(), type: "user" });
    const thinkingId = addMessage({
      sender: "bot",
      content: "Thinking...",
      id: generateId(),
      type: "status",
    });
    thinkingMsgIdRef.current = thinkingId;

    try {
      const bodyPayload: any = {
        question: q,
        mode: effectiveMode, // ⬅️ pass new Mode to backend
        page: 1, // Default to first page
        page_size: 1000 // Default page size
      };

      // Only include selected_db when not in General
      if (effectiveMode !== "General" && effectiveDB) {
        bodyPayload.selected_db = effectiveDB;
      } else {
        // Explicitly ensure General carries no DB
        bodyPayload.selected_db = "";
      }

      // Get auth token from localStorage
      const authToken = localStorage.getItem("authToken");
      
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }

      const res = await fetch("/api/chat", {
        method: "POST",
        headers,
        body: JSON.stringify(bodyPayload),
        signal: controller.signal,
      });

      const payload = await res.json();

      // Phase 4.2: Calculate total response time
      const responseTime = Date.now() - requestStartTime;

      if (!res.ok) {
        const text =
          typeof payload === "string" ? payload : payload?.detail || res.statusText;
        updateMessage(
          thinkingId,
          { error: "HTTPError", message: text } as any,
          {
            type: "error",
            response_time: responseTime,
          }
        );
        setIsTyping(false);
        return;
      }

      // handle backend error envelope
      if (payload?.status === "error" || (payload?.message && !payload?.results)) {
        updateMessage(
          thinkingId,
          {
            error: payload.error, // may be undefined
            message: payload.message ?? "Request failed.",
            sql: payload.sql,
            valid_columns: payload.valid_columns,
            missing_tables: payload.missing_tables,
            suggestions: payload.suggestions,
          } as any,
          {
            type: "error",
            response_time: responseTime,
          }
        );
        setIsTyping(false);
        return;
      }

      // ✅ keep FeedbackBox IDs flowing in non-stream mode
      if (payload?.ids || payload?.turn_id || payload?.chat_id) {
        setLastIds((prev) => ({
          ...prev,
          ...(payload.ids ?? {}),
          ...(payload.turn_id ? { turn_id: payload.turn_id } : {}),
          ...(payload.sql_sample_id ? { sql_sample_id: payload.sql_sample_id } : {}),
          ...(payload.summary_sample_id ? { summary_sample_id: payload.summary_sample_id } : {}), // Fixed property mapping
          ...(payload.chat_id ? { chat_id: payload.chat_id } : {}),
          ...(payload.message_id ? { message_id: payload.message_id } : {})
        }));
      }

      if (payload?.error) {
        // normalize into a consistent object
        const msg: string =
          typeof payload.error === "string"
            ? payload.error
            : payload.error?.message || "Request failed.";
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
          {
            type: "error",
            response_time: responseTime,
          }
        );
        setIsTyping(false);
        return;
      }

      const displayMode: string = payload?.display_mode || "summary";

      // Phase 4.2: Extract hybrid metadata from response
      const hybridMetadata = payload?.hybrid_metadata;

      // 🫧 Prefer morphing the "Thinking..." bubble into the summary if present
      let usedThinkingBubble = false;
      if ((displayMode === "summary" || displayMode === "both") && payload?.summary) {
        updateMessage(thinkingId, payload.summary as string, {
          type: "summary",
          hybrid_metadata: hybridMetadata,
          response_time: responseTime,
        });
        usedThinkingBubble = true;
      }

      // Table message (separate bubble) — add status === "success" guard
      if (
        payload?.status === "success" &&
        (displayMode === "table" || displayMode === "both") &&
        payload?.results?.columns
      ) {
        const columns: string[] = payload.results.columns || [];
        const rows: any[] = payload.results.rows || [];
        
        // Convert array of objects to array of arrays if needed
        let tableRows: (string | number | null)[][] = [];
        if (rows.length > 0) {
          // Check if rows are objects (from backend) or already arrays
          if (typeof rows[0] === 'object' && rows[0] !== null && !Array.isArray(rows[0])) {
            // Convert objects to arrays using column order
            tableRows = rows.map(row => 
              columns.map(col => 
                row[col] !== undefined ? row[col] : null
              )
            );
          } else {
            // Rows are already arrays
            tableRows = rows as (string | number | null)[][];
          }
        }
        
        if (columns.length) {
          addMessage({
            sender: "bot",
            content: [columns, ...tableRows],
            id: generateId(),
            type: "table",
            // Phase 4.2: Add hybrid metadata to table messages too
            hybrid_metadata: hybridMetadata,
            response_time: responseTime,
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
          addMessage({
            sender: "bot",
            content: "⚠️ Error during processing.",
            type: "error",
            id: generateId(),
          });
        }
      }
    } finally {
      setIsTyping(false);
      abortControllerRef.current = null;
      thinkingMsgIdRef.current = null;
      _setIsPaused(false);
    }
  };

  const processFileMessage = async (
    file: File,
    userMessage: string,
    selectedDBArg?: string,
    modeOverride?: Mode
  ) => {
    const q = userMessage.trim();
    if (!q || isTyping) return;

    // Use override if provided, otherwise context mode
    const effectiveMode: Mode = modeOverride ?? mode;

    // If caller provided a DB, trust it; else infer from mode
    const effectiveDB: string =
      typeof selectedDBArg === "string" ? selectedDBArg : resolveDBFromMode(effectiveMode);

    // reset any previous pause and create a fresh controller
    setIsPausedAndAbort(false);
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLastIds({});
    setIsTyping(true);

    // Add file message to chat
    addMessage({
      sender: "user",
      content: q,
      id: generateId(),
      type: "file",
      file: {
        name: file.name,
        size: file.size,
        type: file.type,
      },
    });

    try {
      // Prepare form data for file upload
      const formData = new FormData();
      formData.append("file", file);
      formData.append("question", q);
      formData.append("mode", effectiveMode);
      
      // Only include selected_db when not in General
      if (effectiveMode !== "General" && effectiveDB) {
        formData.append("selected_db", effectiveDB);
      }

      // Get auth token from localStorage
      const authToken = localStorage.getItem("authToken");
      
      const headers: Record<string, string> = {};
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }

      const res = await fetch("/api/file-chat", {
        method: "POST",
        headers,
        body: formData,
        signal: controller.signal,
      });

      const payload = await res.json();

      if (!res.ok) {
        addMessage({
          sender: "bot",
          content: {
            error: "HTTPError",
            message: typeof payload === "string" ? payload : payload?.detail || res.statusText,
          } as any,
          type: "error",
          id: generateId(),
        });
        setIsTyping(false);
        return;
      }

      // handle backend error envelope
      if (payload?.status === "error") {
        addMessage({
          sender: "bot",
          content: {
            error: payload.error,
            message: payload.message ?? "Request failed.",
            sql: payload.sql,
            valid_columns: payload.valid_columns,
          } as any,
          type: "error",
          id: generateId(),
        });
        setIsTyping(false);
        return;
      }

      // ✅ keep FeedbackBox IDs flowing in non-stream mode for file uploads too
      if (payload?.ids || payload?.turn_id || payload?.chat_id) {
        setLastIds((prev) => ({
          ...prev,
          ...(payload.ids ?? {}),
          ...(payload.turn_id ? { turn_id: payload.turn_id } : {}),
          ...(payload.sql_sample_id ? { sql_sample_id: payload.sql_sample_id } : {}),
          ...(payload.summary_sample_id ? { summary_sample_id: payload.summary_sample_id } : {}), // Fixed property mapping
          ...(payload.chat_id ? { chat_id: payload.chat_id } : {}),
          ...(payload.message_id ? { message_id: payload.message_id } : {})
        }));
      }

      // Handle successful file analysis response
      if (payload?.status === "success") {
        // Add summary message if present
        if (payload?.summary) {
          addMessage({
            sender: "bot",
            content: payload.summary,
            type: "summary",
            id: generateId(),
          });
        }

        // Add table message if data is present
        if (payload?.results?.columns && payload?.results?.rows) {
          const columns: string[] = payload.results.columns;
          const rows: any[] = payload.results.rows;
          
          // Convert array of objects to array of arrays if needed
          let tableRows: (string | number | null)[][] = [];
          if (rows.length > 0) {
            // Check if rows are objects (from backend) or already arrays
            if (typeof rows[0] === 'object' && rows[0] !== null && !Array.isArray(rows[0])) {
              // Convert objects to arrays using column order
              tableRows = rows.map(row => 
                columns.map(col => 
                  row[col] !== undefined ? row[col] : null
                )
              );
            } else {
              // Rows are already arrays
              tableRows = rows as (string | number | null)[][];
            }
          }
          
          if (columns.length) {
            addMessage({
              sender: "bot",
              content: [columns, ...tableRows],
              type: "table",
              id: generateId(),
            });
          }
        }
      }
    } catch (err: any) {
      if (err?.name === "AbortError") {
        addMessage({
          sender: "bot",
          content: "⏹️ Stopped.",
          type: "status",
          id: generateId(),
        });
      } else {
        addMessage({
          sender: "bot",
          content: "⚠️ Error during file processing.",
          type: "error",
          id: generateId(),
        });
      }
    } finally {
      setIsTyping(false);
      abortControllerRef.current = null;
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
        processFileMessage,
        isTyping,
        isPaused,
        setIsPaused: setIsPausedAndAbort,
        selectedDB,
        setSelectedDB,
        mode,
        setMode,
        lastIds,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChat must be used within a ChatProvider");
  }
  return context;
};