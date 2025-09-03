// src/components/ChatPanel.tsx
import React, { useEffect, useState } from "react";
import { useChat } from "./ChatContext";
import FeedbackBox from "./FeedbackBox";
import MessageBubble from "./MessageBubble";
import HybridFeedbackBox from "./HybridFeedbackBox";
import DataVisualization from "./DataVisualization";

export default function ChatPanel() {
  const { messages } = useChat();

  // ---- Visualization state ----
  const [showVisualization, setShowVisualization] = useState(false);
  const [visualizationData, setVisualizationData] = useState<{
    columns: string[];
    rows: any[];
  } | null>(null);

  // Detect visualization-ready assistant/bot messages
  useEffect(() => {
    if (!messages || messages.length === 0) return;

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
  }, [messages]);

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
    <div className="flex-1 flex flex-col">
      {/* Scrollable messages area */}
      <div className="flex-1 overflow-auto">
        {/* Centered column like the old version */}
        <div className="mx-auto max-w-3xl w-full px-4 pt-6 pb-28 space-y-3">
          {messages.map((m) => (
            <MessageBubble key={(m as any).id} message={m} />
          ))}

          {/* Visualization toggle and panel (if data available) */}
          {visualizationData && (
            <div className="mt-2">
              <div className="mb-2">
                <button
                  onClick={() => setShowVisualization((s) => !s)}
                  className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm"
                >
                  {showVisualization ? "Show Table" : "Show Chart"}
                </button>
              </div>

              {showVisualization ? (
                <DataVisualization
                  columns={visualizationData.columns}
                  rows={visualizationData.rows}
                  onBackToTable={() => setShowVisualization(false)}
                />
              ) : null}
              {/* When showVisualization is false, we render nothing here,
                  allowing your existing MessageBubble table rendering to remain visible. */}
            </div>
          )}

          {/* tiny spacer so the last bubble never sticks to the edge */}
          <div className="h-2" />
        </div>
      </div>

      {/* Feedback sits above the input, centered with the same width */}
      <div className="mx-auto max-w-3xl w-full px-4 space-y-2">
        {/* Phase 4.2: Hybrid AI feedback for the last hybrid response */}
        {lastHybridMessage && (
          <HybridFeedbackBox
            hybridMetadata={(lastHybridMessage as any).hybrid_metadata}
            onFeedback={handleHybridFeedback}
          />
        )}

        {/* Standard feedback box */}
        <FeedbackBox />
      </div>
    </div>
  );
}
