// src/components/ChatContext.tsx
import React, {
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  ReactNode,
} from "react";

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
};

type Message = {
  sender: "user" | "bot";
  content: string | TableData | OracleError;
  id: string;
  type: "user" | "status" | "summary" | "table" | "error";
};

type LastIds = {
  turn_id?: number;
  sql_sample_id?: number | null;
  summary_sample_id?: number | null;
};

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
  setIsPaused: (val: boolean) => void;
  selectedDB: string;
  setSelectedDB: (db: string) => void;

  // ✅ expose IDs so FeedbackBox or others can post /feedback
  lastIds: LastIds;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [selectedDB, setSelectedDB] = useState("source_db_1");

  // ✅ holds turn/sql/summary IDs for feedback
  const [lastIds, setLastIds] = useState<LastIds>({});

  const abortControllerRef = useRef<AbortController | null>(null);
  const statusMessageIdRef = useRef<string | null>(null);
  const summaryStartedRef = useRef(false);
  const currentSummaryMessageIdRef = useRef<string | null>(null);
  const currentSummaryContentRef = useRef<string>("");

  const generateId = () =>
    `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const addMessage = (message: Message) => {
    const newMessage = { ...message, id: message.id || generateId() };
    setMessages((prev) => [...prev, newMessage]);
    return newMessage.id;
  };

  // allow changing type via overrides
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
    statusMessageIdRef.current = null;
    summaryStartedRef.current = false;
    currentSummaryMessageIdRef.current = null;
    currentSummaryContentRef.current = "";
    setLastIds({}); // ✅ also clear IDs when starting a new chat
  };

  function stageToLabel(phase?: string, stage?: string, sql?: string) {
    const label =
      stage === "sql_gen"
        ? "🧠 Generating SQL…"
        : stage === "sql_ready"
        ? "✅ SQL ready"
        : stage === "validate"
        ? "🔍 Validating SQL…"
        : stage === "validate_ok"
        ? "✅ Validation passed"
        : stage === "execute"
        ? "🏃 Executing query…"
        : stage === "parsing"
        ? "📦 Parsing rows…"
        : stage === "summary_start"
        ? "📝 Generating summary/report…"
        : stage === "summary_stream"
        ? phase || "📝 Summarizing…"
        : stage === "done"
        ? "✅ Done"
        : phase || "Working…";

    if (sql && (stage === "sql_ready" || stage === "execute")) {
      return `${label}\n\n\`\`\`sql\n${sql}\n\`\`\``;
    }
    return label;
  }

  const processMessage = async (userMessage: string, selectedDB: string) => {
    if (!userMessage.trim()) return;

    setIsPaused(false);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    const controller = abortControllerRef.current;

    addMessage({
      sender: "user",
      content: userMessage,
      id: generateId(),
      type: "user",
    });

    // reset transient state
    statusMessageIdRef.current = null;
    summaryStartedRef.current = false;
    currentSummaryMessageIdRef.current = null;
    currentSummaryContentRef.current = "";
    setLastIds({}); // ✅ reset IDs at the beginning of a new question
    setIsTyping(true);

    const rows: TableData = [];
    let columns: string[] = [];
    let displayMode: string | null = null;

    try {
      const response = await fetch("http://localhost:8090/chat/stream", {
        method: "POST",
        body: JSON.stringify({
          question: userMessage,
          selected_db: selectedDB,
        }),
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      if (!reader) throw new Error("No reader available");

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        if (isPaused) {
          controller.abort();
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        // Handle both \n\n and \r\n\r\n chunk boundaries
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.startsWith("data:")) continue;

          let parsed: any;
          try {
            const line = part.replace(/^data:\s*/, "").trim();
            if (!line) continue;
            parsed = JSON.parse(line);
          } catch (e) {
            console.warn("SSE JSON parse warning:", e, part);
            continue;
          }

          // display_mode passthrough
          if (parsed.display_mode) displayMode = parsed.display_mode;

          // ✅ capture IDs from server (turn_ready / sql_sample_ready / summary_sample_ready)
          if (
            parsed.ids &&
            (parsed.stage === "turn_ready" ||
              parsed.stage === "sql_sample_ready" ||
              parsed.stage === "summary_sample_ready")
          ) {
            setLastIds((prev) => ({ ...prev, ...parsed.ids }));
          }
          // ✅ capture final combined IDs packet
          if (parsed.stage === "feedback_ids" && parsed.ids) {
            setLastIds((prev) => ({ ...prev, ...parsed.ids }));
          }

          // Ignore final "done" – summary already shown in same bubble
          if (parsed.stage === "done") {
            if (!summaryStartedRef.current && statusMessageIdRef.current) {
              const id = statusMessageIdRef.current;
              const label = stageToLabel(parsed.phase, parsed.stage);
              updateMessage(id, label, { type: "status" });
              setTimeout(() => {
                setMessages((prev) => prev.filter((m) => m.id !== id));
              }, 300);
            }
            continue;
          }

          // 1) summary_start → keep status bubble; don't morph yet
          if (parsed.stage === "summary_start") {
            if (parsed.display_mode) displayMode = parsed.display_mode;
            const label = stageToLabel(parsed.phase, parsed.stage);
            if (!statusMessageIdRef.current) {
              statusMessageIdRef.current = addMessage({
                sender: "bot",
                content: label,
                id: generateId(),
                type: "status",
              });
            } else {
              updateMessage(statusMessageIdRef.current, label, { type: "status" });
            }
            summaryStartedRef.current = true;
            continue;
          }

          // 2) Status updates (but NOT while streaming summary)
          if (
            parsed.phase &&
            parsed.stage !== "summary_stream" &&
            parsed.stage !== "summary_chunk" &&
            parsed.stage !== "done"
          ) {
            const content = stageToLabel(parsed.phase, parsed.stage, parsed.sql);
            if (!statusMessageIdRef.current) {
              const id = addMessage({
                sender: "bot",
                content,
                id: generateId(),
                type: "status",
              });
              statusMessageIdRef.current = id;
            } else {
              updateMessage(statusMessageIdRef.current, content);
            }
          }

          // 3) Errors
          if (parsed.error) {
            addMessage({
              sender: "bot",
              content: parsed.error as OracleError,
              id: generateId(),
              type: "error",
            });
            setIsTyping(false);
            return;
          }

          // 4) Columns/rows stream
          if (parsed.columns) {
            columns = parsed.columns;
          } else if (parsed.rows) {
            if (Array.isArray(parsed.rows)) rows.push(...parsed.rows);
          }
          if (parsed.partial_results?.rows) {
            if (Array.isArray(parsed.partial_results.rows)) {
              rows.push(...parsed.partial_results.rows);
            }
          }
          if (parsed.results?.columns && Array.isArray(parsed.results.columns)) {
            columns = parsed.results.columns;
          }
          if (parsed.results?.rows && Array.isArray(parsed.results.rows)) {
            rows.push(...parsed.results.rows);
          }

          // 5) Summary chunks (morph on first chunk)
          if (parsed.summary) {
            if (!currentSummaryMessageIdRef.current) {
              if (statusMessageIdRef.current) {
                currentSummaryMessageIdRef.current = statusMessageIdRef.current;
                updateMessage(statusMessageIdRef.current, "", { type: "summary" });
                statusMessageIdRef.current = null;
              } else {
                const id = addMessage({
                  sender: "bot",
                  content: "",
                  id: generateId(),
                  type: "summary",
                });
                currentSummaryMessageIdRef.current = id;
              }
              currentSummaryContentRef.current = "";
            }

            currentSummaryContentRef.current +=
              (currentSummaryContentRef.current ? "\n\n" : "") + parsed.summary;

            updateMessage(
              currentSummaryMessageIdRef.current,
              currentSummaryContentRef.current
            );
            continue;
          }
        }
      }

      // Add table only when not pure-summary and we actually have rows
      if (displayMode !== "summary" && columns.length > 0 && rows.length > 0) {
        addMessage({
          sender: "bot",
          content: [columns, ...rows],
          id: generateId(),
          type: "table",
        });
      }

      setIsTyping(false);
    } catch (err: any) {
      if (err.name !== "AbortError") {
        console.error("Streaming failed:", err);
        addMessage({
          sender: "bot",
          content: "⚠️ Error during processing.",
          type: "summary",
          id: generateId(),
        });
      }
      setIsTyping(false);
    } finally {
      // reset refs (do not remove messages)
      statusMessageIdRef.current = null;
      summaryStartedRef.current = false;
      currentSummaryMessageIdRef.current = null;
      currentSummaryContentRef.current = "";
    }
  };

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
    };
  }, []);

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
        setIsPaused,
        selectedDB,
        setSelectedDB,
        lastIds, // ✅ exposed
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
