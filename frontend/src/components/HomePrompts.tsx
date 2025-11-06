// src/components/HomePrompts.tsx
import React from "react";
import { motion } from "framer-motion";
import { useChat } from "./ChatContext";
import { getPrompts } from "../utils/prompts"; // ← path fixed

export default function HomePrompts() {
  const { processMessage, isTyping, selectedDB, mode } = useChat(); // Add mode from context
  const prompts = getPrompts(selectedDB);

  // Dynamic welcome text based on mode
  const getWelcomeText = () => {
    switch (mode) {
      case "PRAN ERP":
        return "🧠 Welcome! Curious about inventory levels, stock movement, or supply chain insights of PRAN? Just ask";
      case "RFL ERP":
        return "🧠 Welcome! Need quick info on inventory, stock status, or supply chain flow? Ask away - I've got your ERP covered.";
      case "General":
        return "💬 Welcome! Curious about anything beyond business or data? From facts to fun — just ask, I'm all ears.";
      case "SOS":
      default:
        return "🧠 Welcome! Curious about efficiency, performance, or trends? Just ask!";
    }
  };

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto">
      <motion.h2 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="text-2xl font-semibold mb-2 dark:text-gray-100"
      >
        Ask our AI anything
      </motion.h2>
      <motion.p 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.1 }}
        className="text-sm text-gray-500 mb-6 dark:text-gray-400"
      >
        {getWelcomeText()}
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
      className="px-4 py-2 rounded-full bg-transparent text-gray-800 border border-gray-300 text-sm transition duration-200 hover:bg-purple-600 hover:text-white hover:shadow-md disabled:opacity-50 smooth-hover hover-lift button-press dark:text-gray-200 dark:border-gray-600 dark:hover:bg-purple-600"
      onClick={() => onClick(text)}
      disabled={disabled}
    >
      {text}
    </button>
  );
}