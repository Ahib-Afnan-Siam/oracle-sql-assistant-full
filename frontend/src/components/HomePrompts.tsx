import React from "react";
import { useChat } from "./ChatContext";

export default function HomePrompts() {
  const { processMessage, isTyping } = useChat();

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <h2 className="text-2xl font-semibold mb-2">Ask our AI anything</h2>
      <p className="text-sm text-gray-500 mb-6">
        🧠 Welcome! Ask anything about sales, policies, or projects.
      </p>
      <div className="flex flex-wrap gap-4 justify-center">
        <PromptButton
          text="Show floor-wise production and give summary"
          onClick={processMessage}
          disabled={isTyping}
        />
        <PromptButton
          text="List employee names and summarize their salaries"
          onClick={processMessage}
          disabled={isTyping}
        />
      </div>
    </div>
  );
}

function PromptButton({
  text,
  onClick,
  disabled,
}: {
  text: string;
  onClick: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <button
      className="px-4 py-2 rounded-full bg-transparent text-gray-800 border border-gray-300 
                 text-sm transition duration-200 
                 hover:bg-white hover:text-black hover:shadow-md disabled:opacity-50"
      onClick={() => onClick(text)}
      disabled={disabled}
    >
      {text}
    </button>
  );
}
