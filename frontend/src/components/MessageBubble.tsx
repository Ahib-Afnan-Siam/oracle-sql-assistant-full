// src/components/MessageBubble.tsx
import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, User } from "lucide-react";

type Message = {
  sender: "user" | "bot";
  content: string | (string | number | null)[][];
  id: string;
  type: "user" | "status" | "summary" | "table";
};

interface Props {
  message: Message;
}

const MessageBubble: React.FC<Props> = ({ message }) => {
  const { sender, content, type } = message;
  const [displayedContent, setDisplayedContent] = useState("");
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    if (typeof content !== "string") return;
    setDisplayedContent("");
    setCurrentIndex(0);
  }, [content]);

  useEffect(() => {
    if (typeof content !== "string" || currentIndex >= content.length) return;

    const timer = setTimeout(() => {
      setDisplayedContent((prev) => prev + content.charAt(currentIndex));
      setCurrentIndex((prev) => prev + 1);
    }, type === "summary" ? 10 : 0);

    return () => clearTimeout(timer);
  }, [currentIndex, content, type]);

  const bubbleStyle = {
    user: "bg-purple-600 text-white",
    bot: "bg-white text-gray-900 border border-gray-300 shadow-sm",
    status: "bg-yellow-50 text-gray-600 italic",
    table: "bg-white text-gray-900 border border-gray-200 shadow",
    summary: "bg-gray-100 text-gray-800",
  };

  const renderContent = () => {
    if (type === "status") {
      return (
        <div className="flex items-center space-x-2">
          <span className="text-xs animate-pulse">•</span>
          <span className="text-sm">{content}</span>
        </div>
      );
    }

    if (typeof content === "string") {
      const displayText = type === "summary" ? displayedContent : content;
      return (
        <ReactMarkdown
          children={displayText}
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
                {props.children === null || props.children === undefined
                  ? "—"
                  : props.children}
              </td>
            ),
            ol: (props) => <ol className="list-decimal pl-5 my-2" {...props} />,
            ul: (props) => <ul className="list-disc pl-5 my-2" {...props} />,
            li: (props) => <li className="mb-1" {...props} />,
            p: (props) => <p className="my-2" {...props} />,
            strong: (props) => <strong className="font-semibold" {...props} />,
            em: (props) => <em className="italic" {...props} />,
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
                {content[0]?.map((cell, idx) => (
                  <th key={idx} className="border px-2 py-1 font-semibold text-sm">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {content.slice(1).map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j} className="border px-2 py-1 text-sm">
                      {cell === null || cell === undefined ? "—" : cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    return null;
  };

  return (
    <div
      className={`flex items-start space-x-2 px-4 max-w-3xl ${
        sender === "user" ? "ml-auto justify-end flex-row-reverse" : ""
      }`}
    >
      {/* ✅ Avatar section using Lucide icons */}
      <div className="pt-1 flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 shadow-sm">
        {sender === "user" ? (
          <User size={16} className="text-purple-600" />
        ) : (
          <Bot size={16} className="text-gray-600" />
        )}
      </div>

      {/* ✅ Message bubble */}
      <div
        className={`rounded-2xl px-4 py-2 mb-1 text-sm max-w-[80%] ${
          bubbleStyle[type] || bubbleStyle.bot
        }`}
      >
        {renderContent()}
        {type === "summary" &&
          typeof content === "string" &&
          currentIndex < content.length && <span className="animate-pulse">|</span>}
      </div>
    </div>
  );
};

export default MessageBubble;
