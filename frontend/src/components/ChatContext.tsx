import React, {
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  ReactNode,
} from "react";

type TableData = (string | number | null)[][];

type Message = {
  sender: "user" | "bot";
  content: string | TableData;
  id: string;
  type: "user" | "status" | "summary" | "table";
};

interface ChatContextType {
  messages: Message[];
  addMessage: (message: Message) => void;
  updateMessage: (id: string, content: string | TableData) => void; 
  clearMessages: () => void;
  processMessage: (userMessage: string) => void;
  isTyping: boolean;
  isPaused: boolean;
  setIsPaused: (val: boolean) => void;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider = ({ children }: { children: ReactNode }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const statusMessageIdRef = useRef<string | null>(null);
  const summaryStartedRef = useRef(false);
  const currentSummaryMessageIdRef = useRef<string | null>(null);
  const currentSummaryContentRef = useRef<string>("");

  // Generate unique ID for messages
  const generateId = () => `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const addMessage = (message: Message) => {
    const newMessage = { 
      ...message, 
      id: message.id || generateId() 
    };
    setMessages(prev => [...prev, newMessage]);
    return newMessage.id;
  };

  // Update existing message content
  const updateMessage = (id: string, content: string | TableData) => {
    setMessages(prev => 
      prev.map(msg => 
        msg.id === id 
          ? { ...msg, content }
          : msg
      )
    );
  };

  // Clear specific type of messages
  const clearMessagesByType = (type: Message["type"]) => {
    setMessages(prev => prev.filter(msg => msg.type !== type));
  };

  const clearMessages = () => {
    setMessages([]);
    statusMessageIdRef.current = null;
    summaryStartedRef.current = false;
    currentSummaryMessageIdRef.current = null;
    currentSummaryContentRef.current = "";
  };

  const processMessage = async (userMessage: string) => {
    if (!userMessage.trim()) return;

    // Clear any previous abort controller
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    
    // Create new abort controller
    abortControllerRef.current = new AbortController();
    const controller = abortControllerRef.current;

    // Store original query for reference
    const originalQuery = userMessage;
    
    // Add user message
    addMessage({ 
      sender: "user", 
      content: originalQuery, 
      id: generateId(),
      type: "user"
    });
    
    // Reset state
    statusMessageIdRef.current = null;
    summaryStartedRef.current = false;
    currentSummaryMessageIdRef.current = null;
    currentSummaryContentRef.current = "";
    setIsTyping(true);

    const rows: TableData = [];
    let columns: string[] = [];
    let displayMode: string | null = null;

    try {
      // Use original query in API call
      const response = await fetch(
        `http://localhost:8090/chat/stream?question=${encodeURIComponent(originalQuery)}`,
        {
          method: "GET",
          signal: controller.signal,
        }
      );

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

        const parts = buffer.split("\n\n");
        buffer = parts.pop() || "";

        for (const part of parts) {
          if (!part.startsWith("data:")) continue;

          try {
            const line = part.replace(/^data:\s*/, "");
            const parsed = JSON.parse(line);

            // Capture display mode from backend
            if (parsed.display_mode) {
              displayMode = parsed.display_mode;
            }

            // Phase updates
            if (parsed.phase) {
              if (statusMessageIdRef.current) {
                clearMessagesByType("status");
              }
              
              const id = addMessage({ 
                sender: "bot", 
                content: parsed.phase, 
                id: generateId(),
                type: "status"
              });
              statusMessageIdRef.current = id;
            }

            if (parsed.error) {
              clearMessagesByType("status");
              addMessage({ 
                sender: "bot", 
                content: `❌ ${parsed.error}`,
                type: "summary"
              });
              setIsTyping(false);
              return;
            }

            if (parsed.columns) {
              columns = parsed.columns;
            } else if (parsed.rows) {
              rows.push(...parsed.rows);
            }

            // Handle summary chunks
            if (parsed.summary && (displayMode === "summary" || displayMode === "both")) {
              if (!summaryStartedRef.current) {
                clearMessagesByType("status");
                summaryStartedRef.current = true;
              }
              
              if (!currentSummaryMessageIdRef.current) {
                // Create new message for first chunk
                const id = addMessage({ 
                  sender: "bot", 
                  content: parsed.summary, 
                  id: generateId(),
                  type: "summary"
                });
                currentSummaryMessageIdRef.current = id;
                currentSummaryContentRef.current = parsed.summary;
              } else {
                // Append to existing message
                currentSummaryContentRef.current += "\n\n" + parsed.summary;
                updateMessage(
                  currentSummaryMessageIdRef.current, 
                  currentSummaryContentRef.current
                );
              }
            }
          } catch (err) {
            console.error("Streaming JSON parse error:", err, part);
            clearMessagesByType("status");
            addMessage({ 
              sender: "bot", 
              content: "⚠️ JSON parsing error.",
              type: "summary"
            });
            setIsTyping(false);
            return;
          }
        }
      }

      // Clear final status message
      clearMessagesByType("status");
      
      // Add table if displayMode allows it and we have data
      if (displayMode !== "summary" && columns.length > 0 && rows.length > 0) {
        addMessage({ 
          sender: "bot", 
          content: [columns, ...rows],
          id: generateId(),
          type: "table"
        });
      }

      setIsTyping(false);
    } catch (err: any) {
      if (err.name !== "AbortError") {
        console.error("Streaming failed:", err);
        clearMessagesByType("status");
        addMessage({ 
          sender: "bot", 
          content: "⚠️ Error during processing.",
          type: "summary"
        });
      }
      setIsTyping(false);
    } finally {
      statusMessageIdRef.current = null;
      summaryStartedRef.current = false;
      currentSummaryMessageIdRef.current = null;
      currentSummaryContentRef.current = "";
    }
  };

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
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
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = (): ChatContextType => {
  const context = useContext(ChatContext);
  if (!context) throw new Error("useChat must be used within ChatProvider");
  return context;
};