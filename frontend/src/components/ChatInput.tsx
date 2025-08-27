// src/components/ChatInput.tsx
import React, { useState } from "react";
import { PaperPlaneIcon } from "@radix-ui/react-icons";
import { useChat } from "./ChatContext";

export default function ChatInput() {
  const [input, setInput] = useState("");
  const { processMessage, isTyping, isPaused, setIsPaused, selectedDB } = useChat();

  const sendNow = () => {
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;
    processMessage(trimmed, selectedDB);
    setInput("");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendNow();
  };

  const handleKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendNow();
    }
  };

  const handleStop = () => {
    if (isTyping && !isPaused) setIsPaused(true);
  };
  return (
    <form onSubmit={handleSubmit} className="w-full flex justify-center px-4 pb-6 relative z-20">
      <div className="w-full max-w-2xl flex items-center gap-3">
        {/* make the input a positioned container */}
        <div className="relative flex-1">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isTyping}
            type="text"
            placeholder="Ask me anything about your projects"
            className={`w-full py-3 pl-5 pr-14 rounded-full border shadow-sm text-sm placeholder-gray-500 focus:outline-none transition
              ${
                isTyping
                  ? "bg-gray-100 cursor-not-allowed opacity-60"
                  : "bg-white border-gray-300 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              }`}
          />

          {/* SEND — inside the input */}
          <button
            type="submit"
            disabled={isTyping}
            aria-label="Send"
            title="Send"
            className={`absolute right-2 top-1/2 -translate-y-1/2 h-9 w-9 rounded-full flex items-center justify-center shadow transition
              ${
                isTyping
                  ? "bg-gray-300 text-gray-100 cursor-not-allowed"
                  : "bg-[#3b0764] text-white hover:bg-[#4c0a85]"
              }`}
          >
            <PaperPlaneIcon className="h-4 w-4" />
          </button>
        </div>

        {/* STOP — stays outside the input, won’t overlap */}
        <button
          type="button"
          onClick={handleStop}
          disabled={!isTyping}
          className={`px-3 py-2 rounded-lg text-sm transition ${
            isTyping
              ? "bg-red-600 text-white hover:bg-red-700"
              : "opacity-30 cursor-not-allowed bg-gray-100 text-gray-400"
          }`}
          aria-label="Stop"
          title="Stop"
        >
          Stop
        </button>
      </div>
    </form>
  );
}
