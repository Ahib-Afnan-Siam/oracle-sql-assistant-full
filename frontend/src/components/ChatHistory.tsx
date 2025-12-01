// src/components/ChatHistory.tsx
import { useState, useEffect } from "react";
import { useChat } from "./ChatContext";
import clsx from "clsx";

interface ChatHistoryItem {
  query_id: number;
  user_id: string;
  session_id: string;
  user_query: string;
  final_sql: string;
  execution_status: string;
  execution_time_ms: number | null;
  row_count: number | null;
  database_type: string | null;
  query_mode: string | null;
  feedback_type: string | null;
  feedback_comment: string | null;
  created_at: string;
  completed_at: string;
}

export default function ChatHistory() {
  const {
    selectedDB,
    mode,
    processMessage,
    isTyping,
    addMessage,
    updateMessage
  } = useChat();

  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredItem, setHoveredItem] = useState<number | null>(null);

  // Fetch chat history when component mounts or when filters change
  useEffect(() => {
    fetchChatHistory();
  }, [selectedDB, mode]);

  const fetchChatHistory = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = new URLSearchParams();
      if (selectedDB) params.append('database_type', selectedDB);
      if (mode) params.append('query_mode', mode);
      params.append('limit', '50');
      
      // Get auth token from localStorage
      const authToken = localStorage.getItem("authToken");
      
      const headers: Record<string, string> = {};
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }
      
      const response = await fetch(`/api/chat-history?${params.toString()}`, {
        headers,
      });
      
      // Check if response is OK
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.success) {
        setChatHistory(data.queries);
      } else {
        setError(data.detail || "Failed to fetch chat history");
      }
    } catch (err) {
      // More detailed error handling
      if (err instanceof SyntaxError) {
        setError("Failed to parse response from server. The server may be unreachable or returning an unexpected response.");
      } else if (err instanceof Error) {
        setError(`Error fetching chat history: ${err.message}`);
      } else {
        setError("Failed to fetch chat history");
      }
      console.error("Error fetching chat history:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRestoreClick = async (item: ChatHistoryItem) => {
    if (isTyping) return;
    
    try {
      // Get auth token from localStorage
      const authToken = localStorage.getItem("authToken");
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }
      
      // Call the restore endpoint to determine action
      const response = await fetch("/api/chat-history/restore", {
        method: "POST",
        headers,
        body: JSON.stringify({ query_id: item.query_id }),
      });
      
      // Check if response is OK
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.success) {
        if (data.action === "regenerate") {
          // For General Mode, send the query back to the model
          // processMessage will add the user query as a bubble
          processMessage(data.user_query, data.database_type || "", data.query_mode || "" as any);
        } else if (data.action === "execute_sql") {
          // For DB modes, execute the stored SQL directly
          // Add the user query as a chat bubble first
          addMessage({
            sender: "user",
            content: data.user_query,
            id: `user_${Date.now()}`,
            type: "user",
          });
          executeStoredSQL(
            data.final_sql,
            data.user_query,
            data.database_type || "",
            data.query_mode || ""
          );
        }
      } else {
        console.error("Failed to restore chat history item:", data.detail);
      }
    } catch (err) {
      console.error("Error restoring chat history item:", err);
    }
  };

  const executeStoredSQL = async (
    sql: string,
    userQuery: string,
    databaseType: string,
    queryMode: string
  ) => {
    try {
      // Note: We don't add the user query bubble here because it's already added in handleRestoreClick

      // Add a "thinking" message while executing
      const thinkingId = addMessage({
        sender: "bot",
        content: "Executing stored SQL...",
        id: `sql_${Date.now()}`,
        type: "status",
      });
      
      // Get auth token from localStorage
      const authToken = localStorage.getItem("authToken");
      
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }
      
      // Call the execute SQL endpoint
      const response = await fetch("/api/execute-sql", {
        method: "POST",
        headers,
        body: JSON.stringify({
          sql: sql,
          user_query: userQuery,
          database_type: databaseType,
          query_mode: queryMode
        }),
      });
      
      // Check if response is OK
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      if (data.status === "success") {
        // Update the thinking message with results
        if (data.results && data.results.columns && data.results.rows) {
          // Check if results is in the new format (object with columns/rows) or old format (array of arrays)
          if (Array.isArray(data.results)) {
            // Old format - array of arrays
            updateMessage(thinkingId, data.results, {
              type: "table",
              response_time: data.execution_time_ms
            });
          } else {
            // New format - object with columns and rows
            // Check if rows are arrays or objects (ERP system returns objects, SOS returns arrays)
            let rows = data.results.rows;
            if (data.results.rows && data.results.rows.length > 0 && 
                !Array.isArray(data.results.rows[0]) && 
                typeof data.results.rows[0] === 'object') {
              // Convert ERP format (objects) to array format
              rows = data.results.rows.map((row: any) => {
                // Extract values in the same order as columns
                return data.results.columns.map((col: string) => row[col]);
              });
            }
            
            // Convert to old format (array of arrays) for compatibility with updateMessage
            // First row is headers, followed by data rows
            const tableData = [data.results.columns, ...rows];
            
            updateMessage(thinkingId, tableData, {
              type: "table",
              response_time: data.execution_time_ms
            });
          }
        } else {
          updateMessage(thinkingId, "Query executed successfully with no results.", {
            type: "status"
          });
        }
        
        // Remove the visual indicator that this was restored from history
        // addMessage({
        //   sender: "bot",
        //   content: "🔄 Restored result from chat history (re-executed FINAL_SQL)",
        //   type: "status",
        //   id: `restored_${Date.now()}`,
        // });
      } else {
        updateMessage(thinkingId, `Error: ${data.detail || "Failed to execute SQL"}`, {
          type: "error"
        });
      }
    } catch (err) {
      console.error("Error executing stored SQL:", err);
      addMessage({
        sender: "bot",
        content: "⚠️ Error during SQL execution.",
        type: "error",
        id: `error_${Date.now()}`,
      });
    }
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  if (loading) {
    return (
      <div className="py-4 text-center text-gray-500 dark:text-gray-400">
        Loading chat history...
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-4 text-center text-red-500 dark:text-red-400">
        Error: {error}
      </div>
    );
  }

  if (chatHistory.length === 0) {
    return (
      <div className="py-4 text-center text-gray-500 dark:text-gray-400">
        No chat history found
      </div>
    );
  }

  return (
    <div className="mt-4 flex flex-col h-full">
      <div className="text-sm font-semibold text-gray-600 dark:text-gray-300 mb-2">
        Chat History
      </div>
      <div className="space-y-1 flex-1 min-h-0 overflow-y-auto pr-2">
        {chatHistory.map((item) => (
          <button
            key={item.query_id}
            onClick={() => handleRestoreClick(item)}
            disabled={isTyping}
            className={clsx(
              "w-full text-left px-3 py-2 rounded-lg border shadow-sm transition-all duration-300",
              "bg-white/70 text-gray-800 border-white/50",
              "text-xs leading-snug",
              "hover:bg-primary-purple-600 hover:text-white hover:shadow-md smooth-hover",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-purple-600/50",
              "dark:bg-gray-700/70 dark:text-gray-100 dark:border-gray-600/50 dark:hover:bg-primary-purple-600",
              "dark:focus-visible:ring-primary-purple-400/50",
              isTyping && "opacity-60 cursor-not-allowed"
            )}
          >
            <div className="font-medium truncate text-xs">{item.user_query}</div>
            <div className="text-xs opacity-70 mt-1">
              {formatTimestamp(item.created_at)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}