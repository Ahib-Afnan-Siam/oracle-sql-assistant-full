// src/components/ChatPanel.tsx
import { useEffect, useRef } from "react";
import { useChat } from "./ChatContext";
import MessageBubble from "./MessageBubble";
import FeedbackBox from "./FeedbackBox";

export default function ChatPanel() {
  // ✅ call hook INSIDE the component
  const { messages, lastIds, isTyping } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((msg) => (
        <div key={msg.id} className="w-full flex transition-all duration-300 ease-in-out">
          <div
            className={`w-full flex ${
              msg.sender === "user" ? "justify-end pr-4" : "justify-start pl-4"
            }`}
          >
            <MessageBubble message={msg} />
          </div>
        </div>
      ))}

      {/* Show box only after streaming finishes and final feedback IDs exist */}
      {messages.length > 0 &&
        !isTyping &&
        (lastIds?.summary_sample_id || lastIds?.sql_sample_id || lastIds?.turn_id) && (
          <FeedbackBox />
        )}

      <div ref={scrollRef} />
    </div>
  );
}
