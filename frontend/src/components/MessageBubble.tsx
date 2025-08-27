// src/components/MessageBubble.tsx
import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User, Copy, RotateCcw, Check } from "lucide-react";
import DataTable from "./DataTable";
import { useChat } from "./ChatContext";

type OracleError = {
  error: string;
  message?: string;
  code?: string;
  valid_columns?: string[];
  sql?: string;
  missing_tables?: string[];
  suggestion?: string;
  suggestions?: string[];
};

type Message = {
  sender: "user" | "bot";
  content: string | (string | number | null)[][] | OracleError;
  id: string;
  type: "user" | "status" | "summary" | "table" | "error";
};

interface Props {
  message: Message;
}

const OracleErrorDisplay = ({ error }: { error: string | OracleError }) => {
  const errorData: OracleError =
    typeof error === "string" ? { error, message: error } : (error || ({} as OracleError));

  const hasAnyText = !!(errorData.message || errorData.error);

  return (
    <div className="bg-red-50 p-3 rounded-lg border border-red-200">
      <div className="font-bold text-red-800 flex items-start gap-2">
        <span>⚠️</span>
        <span>{hasAnyText ? (errorData.message || errorData.error) : "Unknown error"}</span>
      </div>

      {errorData.code && <div className="text-xs text-red-700 mt-1">Code: {errorData.code}</div>}

      {errorData.missing_tables?.length ? (
        <div className="mt-2">
          <p className="text-sm font-semibold text-gray-700">Missing tables:</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {errorData.missing_tables.map((t) => (
              <span key={t} className="bg-red-100 text-red-800 px-2 py-1 rounded text-xs">
                {t}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {errorData.sql ? (
        <div className="mt-3 bg-gray-800 text-gray-100 p-2 rounded text-xs font-mono overflow-x-auto">
          <div className="text-gray-400 text-xs mb-1">Generated SQL:</div>
          <code>{errorData.sql}</code>
        </div>
      ) : null}

      {errorData.valid_columns?.length ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-gray-700">Available columns:</p>
          <ul className="list-disc pl-5 text-sm text-gray-700 mt-1">
            {errorData.valid_columns.map((col) => (
              <li key={col} className="py-0.5">
                <code className="bg-gray-100 px-1 rounded">{col}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {Array.isArray(errorData.suggestions) && errorData.suggestions.length ? (
        <div className="mt-3">
          <p className="text-sm font-semibold text-gray-700">Suggestions:</p>
          <ul className="list-disc pl-5 text-sm text-gray-700 mt-1">
            {errorData.suggestions.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {errorData.suggestion ? (
        <div className="mt-2 text-sm text-gray-700">
          <span className="font-semibold">Suggestion:</span> {errorData.suggestion}
        </div>
      ) : null}

      <div className="mt-3 text-xs text-gray-500">
        Need help? Try rephrasing your question or check the column names.
      </div>
    </div>
  );
};

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { sender, content, type, id } = message;
  const { processMessage, selectedDB, messages } = useChat();

  // typing effect for summary only
  const [displayed, setDisplayed] = useState("");
  const [idx, setIdx] = useState(0);
  
  // Copy functionality
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

  // Copy function
  const handleCopy = async () => {
    try {
      let textToCopy = "";
      
      if (typeof content === "string") {
        textToCopy = content;
      } else if (Array.isArray(content)) {
        // For table data, create a formatted text representation
        const [headers, ...rows] = content;
        textToCopy = `${headers.join('\t')}\n${rows.map(row => row.join('\t')).join('\n')}`;
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

  // Retry function - finds the last user message and resends it
  const handleRetry = () => {
    // Find the user message that triggered this bot response
    const currentIndex = messages.findIndex(m => m.id === id);
    let userMessage = "";
    
    // Look backwards from current message to find the last user message
    for (let i = currentIndex - 1; i >= 0; i--) {
      if (messages[i].sender === "user" && typeof messages[i].content === "string") {
        userMessage = messages[i].content as string;
        break;
      }
    }
    
    if (userMessage) {
      processMessage(userMessage, selectedDB);
    }
  };

  // Don't show action buttons for user messages, status messages, or during typing
  const showActionButtons = sender === "bot" && 
                           type !== "status" && 
                           !(type === "summary" && typeof content === "string" && idx < content.length);

  const bubbleStyle: Record<Message["type"], string> = {
    user: "bg-purple-600 text-white",
    bot: "bg-white text-gray-900 border border-gray-300 shadow-sm",
    status: "bg-yellow-50 text-gray-600 italic status-blink",
    table: "bg-white text-gray-900 border border-gray-200 shadow",
    summary: "bg-gray-100 text-gray-800",
    error: "bg-red-50 border-red-200",
  };

  const renderContent = () => {
    // thinking / status
    if (type === "status") {
      return <div className="text-sm">{String(content)}</div>;
    }

    // markdown / text
    if (typeof content === "string") {
      if (content.includes("ORA-")) return <OracleErrorDisplay error={content} />;
      const text = type === "summary" ? displayed : content;
      return (
        <ReactMarkdown
          children={text}
          remarkPlugins={[remarkGfm]}
          components={{
            table: (props) => (
              <div className="overflow-x-auto">
                <table className="table-auto border-collapse w-full" {...props} />
              </div>
            ),
            thead: (props) => <thead className="bg-gray-200" {...props} />,
            th: (props) => <th className="border px-2 py-1 font-semibold text-sm" {...props} />,
            td: (props) => <td className="border px-2 py-1 text-sm">{props.children ?? "—"}</td>,
            ol: (props) => <ol className="list-decimal pl-5 my-2" {...props} />,
            ul: (props) => <ul className="list-disc pl-5 my-2" {...props} />,
            li: (props) => <li className="mb-1" {...props} />,
            p: (props) => <p className="my-2" {...props} />,
            strong: (props) => <strong className="font-semibold" {...props} />,
            em: (props) => <em className="italic" {...props} />,
            code: (props) => <code className="bg-gray-100 px-1 rounded font-mono text-sm" {...props} />,
          }}
        />
      );
    }

    // 2D array → rich table
    if (Array.isArray(content)) {
      return <DataTable data={content as (string | number | null)[][]} />;
    }

    // error object
    if (typeof content === "object" && content && ("error" in content || "message" in content)) {
      return <OracleErrorDisplay error={content as OracleError} />;
    }

    return null;
  };

  // widen table bubbles
  const widthClass = type === "table" ? "max-w-[95%]" : "max-w-[78%] md:max-w-[70%]";

  return (
    <div className={`w-full flex ${sender === "user" ? "justify-end" : "justify-start"}`}>
      <div className={`group flex items-start gap-2 ${sender === "user" ? "flex-row-reverse" : ""} max-w-[90%]`}>
        {/* avatar */}
        <div className="pt-1 flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 shadow-sm shrink-0">
          {sender === "user" ? (
            <User size={16} className="text-purple-600" />
          ) : (
            <Bot size={16} className="text-gray-600" />
          )}
        </div>

        {/* For messages without action buttons, use simple bubble structure */}
        {!showActionButtons ? (
          <div className={`rounded-2xl px-4 py-2 text-sm ${widthClass} ${bubbleStyle[type]}`}>
            {renderContent()}
            {type === "summary" && typeof content === "string" && idx < content.length && (
              <span className="animate-pulse">|</span>
            )}
          </div>
        ) : (
          /* For messages with action buttons, use flex column structure */
          <div className="flex flex-col gap-1">
            <div className={`rounded-2xl px-4 py-2 text-sm ${widthClass} ${bubbleStyle[type]}`}>
              {renderContent()}
              {type === "summary" && typeof content === "string" && idx < content.length && (
                <span className="animate-pulse">|</span>
              )}
            </div>
            
            {/* Action buttons for bot messages */}
            <div className="flex items-center gap-1 ml-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              {/* Copy button */}
              <button
                onClick={handleCopy}
                className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors duration-200 flex items-center gap-1"
                title="Copy response"
              >
                {copied ? (
                  <Check size={14} className="text-green-600" />
                ) : (
                  <Copy size={14} className="text-gray-500 hover:text-gray-700" />
                )}
              </button>
              
              {/* Retry button */}
              <button
                onClick={handleRetry}
                className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors duration-200 flex items-center gap-1"
                title="Try again"
              >
                <RotateCcw size={14} className="text-gray-500 hover:text-gray-700" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default MessageBubble;