// src/components/ChatPanel.tsx
import React, { useEffect, useState } from "react";
import { useChat, type Message } from "./ChatContext";
import MessageBubble from "./MessageBubble";
import UnifiedFeedbackBox from "./UnifiedFeedbackBox";
import DataVisualization from "./DataVisualization";
import { BarChart, Table as TableIcon } from "lucide-react"; // Added icon imports
import { motion, AnimatePresence } from "framer-motion"; // Added framer-motion import

function ChatPanel() {
  const { messages, mode } = useChat();

  // ---- Visualization state ----
  const [showVisualization, setShowVisualization] = useState(false);
  const [visualizationData, setVisualizationData] = useState<{
    columns: string[];
    rows: any[];
  } | null>(null);

  // Detect visualization-ready assistant/bot messages
  useEffect(() => {
    // Only show visualization in database mode
    if ((mode !== "SOS" && mode !== "PRAN ERP") || !messages || messages.length === 0) {
      setVisualizationData(null);
      setShowVisualization(false);
      return;
    }

    const latestMessage = messages[messages.length - 1];

    // Support both possible shapes:
    // - Our app's "sender" model: sender === "bot"
    // - Generic "type" model: type === "assistant"
    const isAssistant =
      (latestMessage as any)?.sender === "bot" ||
      (latestMessage as any)?.type === "assistant";

    const wantsViz = Boolean((latestMessage as any)?.visualization === true);
    const results = (latestMessage as any)?.results;

    if (isAssistant && wantsViz && results) {
      const columns: string[] = Array.isArray(results.columns) ? results.columns : [];
      const rows: any[] = Array.isArray(results.rows) ? results.rows : [];

      if (columns.length > 0 && rows.length > 0) {
        setVisualizationData({ columns, rows });
        setShowVisualization(true);
        return;
      }
    }

    // If the latest message does not request visualization, do not force-hide;
    // we keep the user's last toggle choice unless a new viz is provided.
    // However, if a new non-viz assistant message arrives, we can clear viz data.
    if (isAssistant && !wantsViz) {
      setVisualizationData(null);
      setShowVisualization(false);
    }
  }, [messages, mode]);

  // Function to determine if a message should have a feedback box
  const shouldShowFeedbackBox = (message: Message, index: number) => {
    // Only show feedback box for bot messages
    if (message.sender !== "bot") return false;
    
    // Check if this is the last bot message in a sequence
    // Look ahead to see if the next message is also from bot
    const nextMessage = messages[index + 1];
    if (nextMessage && nextMessage.sender === "bot") {
      // If the next message is also from bot, don't show feedback box for this one
      return false;
    }
    
    // Show feedback box for the last bot message in a sequence
    return true;
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Scrollable messages area - Fixed scrolling behavior */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Centered column like the old version - Made responsive */}
        <div className="mx-auto w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl px-4 pt-6 space-y-2">
          {messages.map((m, index) => (
            <React.Fragment key={(m as any).id}>
              <MessageBubble message={m} />
              
              {/* Show unified feedback box only after the last bot message in a sequence */}
              {shouldShowFeedbackBox(m, index) && (
                <div className="px-4 space-y-2">
                  <UnifiedFeedbackBox 
                    messageId={(m as any).id}
                    hybridMetadata={(m as any).hybrid_metadata}
                  />
                </div>
              )}
            </React.Fragment>
          ))}

          {/* Visualization toggle and panel (if data available and in database mode) */}
          {(mode === "SOS" || mode === "PRAN ERP") && visualizationData && (
            <div className="mt-2">
              <div className="mb-2">
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => setShowVisualization((s) => !s)}
                  className="px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700 text-sm flex items-center gap-1 smooth-hover hover-lift dark:bg-purple-700 dark:hover:bg-purple-800"
                >
                  {showVisualization ? (
                    <>
                      <TableIcon size={16} />
                      Show Table
                    </>
                  ) : (
                    <>
                      <BarChart size={16} />
                      Show Chart
                    </>
                  )}
                </motion.button>
              </div>

              <AnimatePresence mode="wait">
                {showVisualization && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <DataVisualization
                      columns={visualizationData.columns}
                      rows={visualizationData.rows}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
              {/* When showVisualization is false, we render nothing here,
                  allowing your existing MessageBubble table rendering to remain visible. */}
            </div>
          )}

          {/* tiny spacer so the last bubble never sticks to the edge */}
          <div className="h-24" />
        </div>
      </div>
    </div>
  );
}

export default ChatPanel;