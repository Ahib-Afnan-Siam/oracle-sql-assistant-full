// src/components/MessageBubble.tsx
import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User } from "lucide-react";

type OracleError = {
  error: string;
  message?: string;
  valid_columns?: string[];
  sql?: string;
  missing_tables?: string[];
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
  let errorData: OracleError | null = null;
  try {
    errorData = typeof error === "string" ? JSON.parse(error) : error;
  } catch {
    errorData = {
      error: typeof error === "string" ? error : "Unknown error",
      message: typeof error === "string" ? error : "An unexpected error occurred",
    };
  }

  if (!errorData?.error) {
    return (
      <div className="text-red-600">
        ⚠️ {typeof error === "string" ? error : "Unknown error"}
      </div>
    );
  }

  return (
    <div className="bg-red-50 p-3 rounded-lg border border-red-200">
      <div className="font-bold text-red-800 flex items-start gap-2">
        <span>⚠️</span>
        <span>{errorData.message || errorData.error}</span>
      </div>

      {errorData.missing_tables?.length ? (
        <div className="mt-2">
          <p className="text-sm font-semibold text-gray-700">Missing tables:</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {errorData.missing_tables.map((t: string) => (
              <span
                key={t}
                className="bg-red-100 text-red-800 px-2 py-1 rounded text-xs"
              >
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
            {errorData.valid_columns.map((col: string) => (
              <li key={col} className="py-0.5">
                <code className="bg-gray-100 px-1 rounded">{col}</code>
              </li>
            ))}
          </ul>
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

  // typing effect for summary only
  const [displayed, setDisplayed] = useState("");
  const [idx, setIdx] = useState(0);

  // reset when a new message arrives or the type changes
  useEffect(() => {
    if (type !== "summary") return;
    setDisplayed("");
    setIdx(0);
  }, [id, type]);

  // type until we reach current content length
  useEffect(() => {
    if (type !== "summary" || typeof content !== "string") return;
    if (idx >= content.length) return;

    const t = setTimeout(() => {
      setDisplayed(content.slice(0, idx + 1));
      setIdx((v) => v + 1);
    }, 10);

    return () => clearTimeout(t);
  }, [idx, content, type]);

  const bubbleStyle: Record<Message["type"], string> = {
    user: "bg-purple-600 text-white",
    bot: "bg-white text-gray-900 border border-gray-300 shadow-sm",
    status: "bg-yellow-50 text-gray-600 italic",
    table: "bg-white text-gray-900 border border-gray-200 shadow",
    summary: "bg-gray-100 text-gray-800",
    error: "bg-red-50 border-red-200",
  };

  const renderContent = () => {
    if (type === "status") {
      return (
        <div className="flex items-center space-x-2">
          <span className="text-xs animate-pulse">•</span>
          <span className="text-sm">{String(content)}</span>
        </div>
      );
    }

    if (typeof content === "string") {
      if (content.startsWith("{") || (content.includes("ORA-") && content.includes(":"))) {
        return <OracleErrorDisplay error={content} />;
      }

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
            th: (props) => (
              <th className="border px-2 py-1 font-semibold text-sm" {...props} />
            ),
            td: (props) => (
              <td className="border px-2 py-1 text-sm">
                {props.children ?? "—"}
              </td>
            ),
            ol: (props) => <ol className="list-decimal pl-5 my-2" {...props} />,
            ul: (props) => <ul className="list-disc pl-5 my-2" {...props} />,
            li: (props) => <li className="mb-1" {...props} />,
            p: (props) => <p className="my-2" {...props} />,
            strong: (props) => <strong className="font-semibold" {...props} />,
            em: (props) => <em className="italic" {...props} />,
            code: (props) => (
              <code className="bg-gray-100 px-1 rounded font-mono text-sm" {...props} />
            ),
          }}
        />
      );
    }

    if (Array.isArray(content)) {
      return (
        <div className="overflow-x-auto">
          <table className="table-auto border-collapse w-full">
            <thead className="bg-gray-200">
              <tr>
                {content[0]?.map((cell, i) => (
                  <th key={i} className="border px-2 py-1 font-semibold text-sm">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {content.slice(1).map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c} className="border px-2 py-1 text-sm">
                      {cell ?? "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    if (typeof content === "object" && content && "error" in content) {
      return <OracleErrorDisplay error={content} />;
    }

    return null;
  };

  return (
    <div
      className={`flex items-start space-x-2 px-4 max-w-3xl ${
        sender === "user" ? "ml-auto justify-end flex-row-reverse" : ""
      }`}
    >
      <div className="pt-1 flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 shadow-sm">
        {sender === "user" ? (
          <User size={16} className="text-purple-600" />
        ) : (
          <Bot size={16} className="text-gray-600" />
        )}
      </div>

      <div
        className={`rounded-2xl px-4 py-2 mb-1 text-sm max-w-[80%] ${
          bubbleStyle[type]
        }`}
      >
        {renderContent()}
        {type === "summary" &&
          typeof content === "string" &&
          idx < content.length && <span className="animate-pulse">|</span>}
      </div>
    </div>
  );
};

export default MessageBubble;
