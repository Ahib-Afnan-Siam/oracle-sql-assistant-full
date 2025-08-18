// src/components/ChatInput.tsx
import React, { useState } from "react";
import { PaperPlaneIcon } from "@radix-ui/react-icons";
import { useChat } from "./ChatContext";

export default function ChatInput() {
  const [input, setInput] = useState("");
  const {
    processMessage,
    isTyping,
    isPaused,
    setIsPaused,
    selectedDB, // ✅ get selected DB from context
  } = useChat();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;

    // ✅ Send both message and selected_db
    processMessage(trimmed, selectedDB);
    setInput("");
  };

  return (
    <form onSubmit={handleSubmit} className="w-full flex justify-center px-4 pb-6">
      <div className="relative w-full max-w-2xl flex items-center space-x-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isTyping}
          type="text"
          placeholder="Ask me anything about your projects"
          className={`flex-1 py-3 pl-5 pr-12 rounded-full border shadow-sm text-sm placeholder-gray-500 focus:outline-none transition
            ${isTyping
              ? "bg-gray-100 cursor-not-allowed opacity-60"
              : "bg-white border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"}`}
        />

        {/* ⏹ Stop button appears only while generating and not paused */}
        {isTyping && !isPaused && (
          <button
            type="button"
            onClick={() => setIsPaused(true)}
            className="absolute right-20 top-1/2 -translate-y-1/2 z-10 bg-red-500 hover:bg-red-600 text-white rounded px-3 py-1 text-sm shadow-md transition"
            title="Stop typing"
          >
            ⏹ Stop
          </button>
        )}

        <button
          type="submit"
          disabled={isTyping}
          className={`absolute right-2 top-1/2 -translate-y-1/2 p-2 text-gray-500 hover:text-blue-600 transition
            ${isTyping ? "opacity-30 cursor-not-allowed" : ""}`}
        >
          <PaperPlaneIcon className="h-5 w-5" />
        </button>
      </div>
    </form>
  );
}
