// src/components/HomePrompts.tsx
import React from "react";
import { motion } from "framer-motion";
import { useChat } from "./ChatContext";
import { getPrompts } from "../utils/prompts"; // ← path fixed

export default function HomePrompts() {
  const { processMessage, isTyping, selectedDB, mode } = useChat(); // Add mode from context
  const prompts = getPrompts(selectedDB);

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4">
      <motion.h2 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="text-2xl font-semibold mb-2"
      >
        Ask our AI anything
      </motion.h2>
      <motion.p 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="text-sm text-gray-500 mb-6"
      >
        🧠 Welcome! Curious about efficiency, performance, or trends? Just ask!
      </motion.p>
      <div className="flex flex-wrap gap-4 justify-center">
        {prompts.map((text, index) => (
          <motion.div
            key={text}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 * index }}
            className="staggered-animation"
          >
            <PromptButton
              text={text}
              onClick={(t) => processMessage(t, selectedDB, mode)} // Pass mode to processMessage
              disabled={isTyping}
            />
          </motion.div>
        ))}
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
      className="px-4 py-2 rounded-full bg-transparent text-gray-800 border border-gray-300 text-sm transition duration-200 hover:bg-purple-600 hover:text-white hover:shadow-md disabled:opacity-50 smooth-hover hover-lift button-press"
      onClick={() => onClick(text)}
      disabled={disabled}
    >
      {text}
    </button>
  );
}