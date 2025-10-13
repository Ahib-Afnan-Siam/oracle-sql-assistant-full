// src/components/ChatPanel.tsx
import React, { useEffect, useState } from "react";
import { useChat, type Message } from "./ChatContext";
import FeedbackBox from "./FeedbackBox";
import MessageBubble from "./MessageBubble";
import HybridFeedbackBox from "./HybridFeedbackBox";
import DataVisualization from "./DataVisualization";
import { BarChart, Table as TableIcon } from "lucide-react"; // Added icon imports
import { motion, AnimatePresence } from "framer-motion"; // Added framer-motion import

export default function ChatPanel() {
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
    if ((mode !== "SOS" && mode !== "Test DB") || !messages || messages.length === 0) {
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

  // Phase 4.2: Find the last message with hybrid metadata for hybrid feedback
  const lastHybridMessage = [...messages]
    .reverse()
    .find(
      (m) =>
        (m as any).sender === "bot" &&
        (m as any).hybrid_metadata &&
        Object.keys((m as any).hybrid_metadata).length > 0
    );

  const handleHybridFeedback = (feedback: any) => {
    // Log hybrid-specific feedback
    console.log("Hybrid AI Feedback:", {
      message_id: (lastHybridMessage as any)?.id,
      hybrid_metadata: (lastHybridMessage as any)?.hybrid_metadata,
      feedback,
    });

    // TODO: Send to backend for analytics
    // This could be integrated with the existing feedback system
    // or sent to a separate hybrid AI analytics endpoint
  };

  return (
    <div className="flex-1 flex flex-col h-full">
      {/* Scrollable messages area - Fixed scrolling behavior */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Centered column like the old version */}
        <div className="mx-auto max-w-3xl w-full px-4 pt-6 space-y-2">
          {messages.map((m, index) => (
            <React.Fragment key={(m as any).id}>
              <MessageBubble message={m} />
              
              {/* Show feedback boxes only after bot messages */}
              {m.sender === "bot" && (
                <div className="px-4 space-y-2">
                  {/* Phase 4.2: Hybrid AI feedback for the last hybrid response */}
                  {lastHybridMessage && (lastHybridMessage as any).id === (m as any).id && (
                    <HybridFeedbackBox
                      hybridMetadata={(lastHybridMessage as any).hybrid_metadata}
                      onFeedback={handleHybridFeedback}
                    />
                  )}
                  
                  {/* Standard feedback box for bot messages */}
                  <FeedbackBox messageId={(m as any).id} />
                </div>
              )}
            </React.Fragment>
          ))}

          {/* Visualization toggle and panel (if data available and in database mode) */}
          {(mode === "SOS" || mode === "Test DB") && visualizationData && (
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