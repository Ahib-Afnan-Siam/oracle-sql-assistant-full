// src/components/ChatPanel.tsx

import { useEffect, useRef } from "react";
import { useChat } from "./ChatContext";
import MessageBubble from "./MessageBubble";

export default function ChatPanel() {
  const { messages } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((msg, idx) => (
        <div
          key={idx}
          className="w-full flex transition-all duration-300 ease-in-out"
        >
          <div
            className={`w-full flex ${
              msg.sender === "user" ? "justify-end pr-4" : "justify-start pl-4"
            }`}
          >
            <MessageBubble message={msg} />
          </div>
        </div>
      ))}
      <div ref={scrollRef} />
    </div>
  );
}
