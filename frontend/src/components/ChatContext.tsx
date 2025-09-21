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

type LastIds = { turn_id?: number; sql_sample_id?: number | null; sql_summary_id?: number | null };

// New Mode type - reordered to reflect preference
export type Mode = "SOS" | "General" | "Test DB";

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
  // Default DB changed to SOS mode
  const [selectedDB, setSelectedDB] = useState<string>("source_db_1");
  // 🔁 New default mode - changed to SOS
  const [mode, setMode] = useState<Mode>("SOS");
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
    if (m === "Test DB") return "source_db_2";
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
      };

      // Only include selected_db when not in General
      if (effectiveMode !== "General" && effectiveDB) {
        bodyPayload.selected_db = effectiveDB;
      } else {
        // Explicitly ensure General carries no DB
        bodyPayload.selected_db = "";
      }

      const res = await fetch("http://127.0.0.1:8090/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
        const rows: any[][] = payload.results.rows || [];
        if (columns.length) {
          addMessage({
            sender: "bot",
            content: [columns, ...(rows || [])],
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
        type: file.type
      }
    });

    const thinkingId = addMessage({
      sender: "bot",
      content: "Analyzing file...",
      id: generateId(),
      type: "status",
    });
    thinkingMsgIdRef.current = thinkingId;

    try {
      // Phase 4.2: Track request start time for response time calculation
      const requestStartTime = Date.now();
      
      // First, upload the file
      const formData = new FormData();
      formData.append('file', file);
      
      const uploadResponse = await fetch("http://127.0.0.1:8090/upload-file", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      if (!uploadResponse.ok) {
        throw new Error(`File upload failed: ${uploadResponse.statusText}`);
      }

      const uploadResult = await uploadResponse.json();
      
      // Then, analyze the file with the user's question
      const analyzePayload = {
        file_id: uploadResult.file_id,
        question: q
      };

      const analyzeResponse = await fetch("http://127.0.0.1:8090/analyze-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(analyzePayload),
        signal: controller.signal,
      });

      const payload = await analyzeResponse.json();

      // Phase 4.2: Calculate total response time
      const responseTime = Date.now() - requestStartTime;

      if (!analyzeResponse.ok) {
        const text =
          typeof payload === "string" ? payload : payload?.detail || analyzeResponse.statusText;
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
      if (payload?.status === "error") {
        updateMessage(
          thinkingId,
          {
            error: payload.error, // may be undefined
            message: payload.message ?? "Request failed.",
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
          typeof payload.error === "string"
            ? payload.error
            : payload.error?.message || "Request failed.";
        updateMessage(
          thinkingId,
          {
            error: "FileAnalysisError",
            message: msg,
          } as any,
          {
            type: "error",
            response_time: responseTime,
          }
        );
        setIsTyping(false);
        return;
      }

      // Phase 4.2: Extract hybrid metadata from response
      const hybridMetadata = payload?.hybrid_metadata;

      // Update the thinking bubble with the analysis result
      updateMessage(thinkingId, payload.summary as string, {
        type: "summary",
        hybrid_metadata: hybridMetadata,
        response_time: responseTime,
      });
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
          updateMessage(thinkingMsgIdRef.current, "⚠️ Error during file processing.", { type: "error" });
        } else {
          addMessage({
            sender: "bot",
            content: "⚠️ Error during file processing.",
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

  // Helper function to read file as base64
  const readFileAsBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        // Remove the data URL prefix (e.g., "data:image/png;base64,")
        const base64Content = result.split(',')[1];
        resolve(base64Content);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
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

export const useChat = (): ChatContextType => {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
};
