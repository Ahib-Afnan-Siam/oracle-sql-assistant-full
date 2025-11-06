// src/components/MessageBubble.tsx
import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, Copy, RotateCcw, Check, Paperclip } from "lucide-react";
import DataTable from "./DataTable";
import PaginatedDataTable from "./PaginatedDataTable";
import { useChat } from "./ChatContext";
import HybridMetadataDisplay from "./HybridMetadataDisplay";
import clsx from "clsx";
import { motion, AnimatePresence } from "framer-motion";

type OracleError = {
  code?: string;
  error?: string;
  message?: string;
  sql?: string;
  missing_tables?: string[];
  valid_columns?: string[];
  suggestion?: string;
  suggestions?: string[];
};

type HybridMetadata = {
  processing_mode?: string;
  model_used?: string;
  selection_reasoning?: string;
  processing_time?: number;
  local_confidence?: number;
  api_confidence?: number;
};

type TableData = (string | number | null)[][];

type MessageFile = {
  name: string;
  size: number;
  type: string;
  content?: string; // base64 encoded content for images
};

type Message = {
  sender: "user" | "bot";
  content: string | TableData | OracleError;
  id: string;
  type: "user" | "status" | "summary" | "table" | "error" | "file";
  hybrid_metadata?: HybridMetadata;
  response_time?: number;
  file?: MessageFile;
};

interface Props {
  message: Message;
};

const OracleErrorDisplay = ({ error }: { error: string | OracleError }) => {
  const errorData: OracleError =
    typeof error === "string" ? { error, message: error } : (error || ({} as OracleError));

  const hasAnyText = !!(errorData.message || errorData.error);

  return (
    <div className="bg-red-50 p-3 rounded-lg border border-red-200 dark:bg-red-900/30 dark:border-red-800/50 dark:text-gray-100">
      <div className="font-bold text-red-800 flex items-start gap-2 dark:text-red-200">
        <span>⚠️</span>
        <span>{hasAnyText ? (errorData.message || errorData.error) : "Unknown error"}</span>
      </div>

      {errorData.code && <div className="text-xs text-red-700 mt-1 dark:text-red-300">Code: {errorData.code}</div>}

      {errorData.missing_tables?.length ? (
        <div className="mt-2">
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">Missing tables:</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {errorData.missing_tables.map((t) => (
              <span key={t} className="bg-red-100 text-red-800 px-2 py-1 rounded text-xs dark:bg-red-800/30 dark:text-red-200">
                {t}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {errorData.sql ? (
        <div className="mt-3 bg-gray-800 text-gray-100 p-2 rounded text-xs font-mono overflow-x-auto dark:bg-gray-700">
          <div className="text-gray-400 text-xs mb-1 dark:text-gray-300">Generated SQL:</div>
          <code>{errorData.sql}</code>
        </div>
      ) : null}

      {errorData.valid_columns?.length ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">Available columns:</p>
          <ul className="list-disc pl-5 text-sm text-gray-700 mt-1 dark:text-gray-300">
            {errorData.valid_columns.map((col) => (
              <li key={col} className="py-0.5">
                <code className="bg-gray-100 px-1 rounded dark:bg-gray-700 dark:text-gray-300">{col}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {Array.isArray(errorData.suggestions) && errorData.suggestions.length ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-gray-700 dark:text-gray-300">Suggestions:</p>
          <ul className="list-disc pl-5 text-sm text-gray-700 mt-1 dark:text-gray-300">
            {errorData.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {errorData.suggestion ? (
        <div className="mt-2 text-sm text-gray-700 dark:text-gray-300">
          <span className="font-semibold">Suggestion:</span> {errorData.suggestion}
        </div>
      ) : null}

      <div className="mt-3 text-xs text-gray-500 dark:text-gray-400">
        Need help? Try rephrasing your question or check the column names.
      </div>
    </div>
  );
};

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { sender, content, type, id, file } = message;
  const { processMessage, selectedDB, mode, messages } = useChat();

  const [displayed, setDisplayed] = useState("");
  const [idx, setIdx] = useState(0);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (type !== "summary") return;
    setDisplayed("");
    setIdx(0);
  }, [id, type]);

  useEffect(() => {
    if (type !== "summary" || typeof content !== "string") return;
    if (idx >= content.length) return;
    const t = setTimeout(() => {
      setDisplayed(content.slice(0, idx + 1));
      setIdx((v) => v + 1);
    }, 10);
    return () => clearTimeout(t);
  }, [idx, content, type]);

  const handleCopy = async () => {
    try {
      let textToCopy = "";
      if (typeof content === "string") {
        textToCopy = content;
      } else if (Array.isArray(content)) {
        const [headers, ...rows] = content;
        textToCopy = `${headers.join("\t")}\n${rows.map((row) => row.join("\t")).join("\n")}`;
      } else if (typeof content === "object" && content && ("error" in content || "message" in content)) {
        const errorData = content as OracleError;
        textToCopy = errorData.message || errorData.error || "Error occurred";
      }
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleRetry = () => {
    const currentIndex = messages.findIndex((m) => m.id === id);
    let userMessage = "";
    for (let i = currentIndex - 1; i >= 0; i--) {
      if (messages[i].sender === "user" && typeof messages[i].content === "string") {
        userMessage = messages[i].content as string;
        break;
      }
    }
    if (userMessage) processMessage(userMessage, selectedDB, mode);
  };

  // Show action buttons for all bot messages except status messages
  // For summary messages, show buttons only when typing is complete
  const showActionButtons = 
    sender === "bot" && 
    type !== "status" && 
    (type !== "summary" || typeof content !== "string" || idx >= content.length);

  const bubbleStyle: Record<Message["type"], string> = {
    user: "bg-primary-purple-600 text-white",
    status: "bg-yellow-50 text-gray-600 italic status-blink dark:bg-yellow-900/30 dark:text-gray-100",
    table: "bg-white text-gray-900 border border-gray-200 shadow dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700",
    summary: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-100",
    error: "bg-red-50 border-red-200 dark:bg-red-900/20 dark:border-red-800/50 dark:text-gray-100",
    file: "bg-blue-50 text-gray-800 border border-blue-200 dark:bg-blue-900/20 dark:text-gray-100 dark:border-blue-800/50",
  };

// Wider rules for tables; narrower for text bubbles
const bubbleMaxWidth =
  type === "table"
    ? "w-full max-w-[1200px] sm:max-w-[95%] md:max-w-[90%] lg:max-w-[85%] xl:max-w-[80%] 2xl:max-w-[75%]" // wide but bounded
    : "max-w-full sm:max-w-[90%] md:max-w-[80%] lg:max-w-[70%] xl:max-w-[65%] 2xl:max-w-[60%]";

const tableMaxWidthStyle =
  message.type === "table"
    ? { maxWidth: "min(1200px, calc(100vw - 4rem))" }
    : undefined;

  // Enhanced visual distinction between user and bot messages
  const getUserBubbleStyle = () => {
    return clsx(
      "rounded-3xl px-4 py-3 shadow-md break-words",
      "bg-gradient-to-r from-primary-purple-600 to-primary-purple-700 text-white",
      "flex flex-col",
      type === "table" && "overflow-hidden"
    );
  };

  const getBotBubbleStyle = () => {
    return clsx(
      "rounded-2xl px-4 py-3 shadow-sm break-words",
      bubbleStyle[type],
      "flex flex-col",
      type === "table" && "overflow-hidden"
    );
  };

  const renderContent = () => {
    if (type === "file") {
      return (
        <div className="flex items-center gap-2">
          <Paperclip size={16} className="text-blue-500 dark:text-blue-400" />
          <div>
            <div className="font-medium">{file?.name}</div>
            {file && (
              <div className="text-xs text-blue-100 dark:text-blue-300">
                {(file.size / 1024).toFixed(1)} KB
              </div>
            )}
          </div>
        </div>
      );
    }

    if (type === "status") {
      return <div className="text-sm">{String(content)}</div>;
    }

    if (type === "error") {
      return <OracleErrorDisplay error={content as OracleError} />;
    }

    if (type === "table") {
      // Always show table data regardless of current mode
      // The mode check was preventing table display when switching modes
      // Check if we have metadata that indicates server-side pagination is available
      const tableData = content as TableData;
      const hasPaginationMetadata = 
        Array.isArray(tableData) && 
        tableData.length > 0 && 
        typeof tableData[tableData.length - 1] === 'object' && 
        (tableData[tableData.length - 1] as any).metadata;
      
      if (hasPaginationMetadata) {
        // Use paginated data table for large datasets
        // Extract the question from the previous user message
        const currentIndex = messages.findIndex((m) => m.id === message.id);
        let question = "";
        for (let i = currentIndex - 1; i >= 0; i--) {
          if (messages[i].sender === "user" && typeof messages[i].content === "string") {
            question = messages[i].content as string;
            break;
          }
        }
        
        return <PaginatedDataTable 
          initialData={tableData} 
          question={question}
          mode={mode}
          selectedDB={selectedDB}
        />;
      } else {
        // Use regular data table for smaller datasets
        return <DataTable data={tableData} />;
      }
    }

    if (type === "summary") {
      const text = displayed;
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert dark:text-gray-100">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {text}
          </ReactMarkdown>
        </div>
      );
    }

    // For general mode responses that are strings (not tables or errors)
    if (typeof content === "string") {
      return (
        <div className="prose prose-sm max-w-none dark:prose-invert dark:text-gray-100">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {content}
          </ReactMarkdown>
        </div>
      );
    }

    // Fallback for any other content
    return <div className="text-sm dark:text-gray-100">{String(content)}</div>;
  };

  return (
    <div
      className={clsx(
        "flex",
        sender === "user" ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={clsx(
          "flex gap-3 max-w-full",
          bubbleMaxWidth,
          type === "table" && "mx-auto",          // center wide table bubbles
          sender === "user" ? "flex-row-reverse" : "flex-row"
        )}
      >
        {/* Avatar */}
        <div
          className={clsx(
            "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white",
            sender === "user" 
              ? "bg-gradient-to-r from-primary-purple-500 to-primary-purple-600" 
              : "bg-gradient-to-r from-primary-purple-700 to-primary-purple-800"
          )}
        >
          {sender === "user" ? <User size={18} /> : <Bot size={18} />}
        </div>

        {/* Bubble */}
        <div
          className={sender === "user" ? getUserBubbleStyle() : getBotBubbleStyle()}
          style={tableMaxWidthStyle}
        >
          {renderContent()}

          {/* Hybrid metadata display - only for bot messages with metadata */}
          {sender === "bot" && (message as any).hybrid_metadata && (
            <HybridMetadataDisplay metadata={(message as any).hybrid_metadata} />
          )}

          {/* Response time display */}
          {(message as any).response_time && (
            <div className="text-xs text-gray-500 mt-2 dark:text-gray-400">
              Response time: {(message as any).response_time}ms
            </div>
          )}

          {/* Action buttons (copy/retry) - only for bot messages */}
          <AnimatePresence>
            {showActionButtons && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.2 }}
                className="flex gap-1 mt-2 self-end"
              >
                <button
                  onClick={handleCopy}
                  className="p-1.5 rounded-full action-button hover-scale-strong focus:outline-none focus:ring-2 focus:ring-purple-500 button-press"
                  title="Copy message"
                  aria-label="Copy message"
                >
                  {copied ? <Check size={16} className="action-button-icon" /> : <Copy size={16} className="action-button-icon" />}
                </button>
                <button
                  onClick={handleRetry}
                  className="p-1.5 rounded-full action-button hover-scale-strong focus:outline-none focus:ring-2 focus:ring-purple-500 button-press"
                  title="Retry message"
                  aria-label="Retry message"
                >
                  <RotateCcw size={16} className="action-button-icon" />
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;