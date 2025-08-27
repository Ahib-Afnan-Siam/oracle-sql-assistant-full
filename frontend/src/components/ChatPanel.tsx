// src/components/ChatPanel.tsx
import React from "react";
import { useChat } from "./ChatContext";
import FeedbackBox from "./FeedbackBox";
import MessageBubble from "./MessageBubble";

export default function ChatPanel() {
  const { messages } = useChat();

  return (
    <div className="flex-1 flex flex-col">
      {/* Scrollable messages area */}
      <div className="flex-1 overflow-auto">
        {/* Centered column like the old version */}
        <div className="mx-auto max-w-3xl w-full px-4 pt-6 pb-28 space-y-3">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {/* tiny spacer so the last bubble never sticks to the edge */}
          <div className="h-2" />
        </div>
      </div>

      {/* Feedback sits above the input, centered with the same width */}
      <div className="mx-auto max-w-3xl w-full px-4">
        <FeedbackBox />
      </div>
    </div>
  );
}
