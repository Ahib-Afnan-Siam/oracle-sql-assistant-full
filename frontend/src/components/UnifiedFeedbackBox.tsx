// src/components/UnifiedFeedbackBox.tsx
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThumbsUp, ThumbsDown, MessageSquare } from "lucide-react";
import { useChat } from "./ChatContext";

type HybridMetadata = {
  processing_mode?: string;
  model_used?: string;
  selection_reasoning?: string;
  processing_time?: number;
  local_confidence?: number;
  api_confidence?: number;
};

interface Props {
  messageId?: string;
  hybridMetadata?: HybridMetadata;
  turnId?: number; // Accept turnId as prop
  sqlSampleId?: number | null; // Accept sqlSampleId as prop
  summary_sample_id?: number | null; // Accept summarySampleId as prop
  chatId?: number; // Accept chatId as prop
  messageIdForFeedback?: number; // Accept messageId as prop
}

const UnifiedFeedbackBox: React.FC<Props> = ({ 
  messageId, 
  hybridMetadata,
  turnId: propTurnId, // Use prop turnId if provided
  sqlSampleId: propSqlSampleId, // Use prop sqlSampleId if provided
  summary_sample_id: propSummarySampleId, // Use prop summarySampleId if provided
  chatId: propChatId, // Use prop chatId if provided
  messageIdForFeedback: propMessageId // Use prop messageId if provided
}) => {
  const { lastIds, messages } = useChat();
  
  // Use prop values if provided, otherwise fall back to context values
  const turnId = propTurnId ?? lastIds?.turn_id;
  const sqlSampleId = propSqlSampleId ?? lastIds?.sql_sample_id ?? null;
  const summarySampleId = propSummarySampleId ?? lastIds?.summary_sample_id ?? null; // Use correct property name
  const chatId = propChatId ?? lastIds?.chat_id;
  const messageIdForFeedback = propMessageId ?? lastIds?.message_id;

  // Find the message corresponding to this feedback box
  const currentMessage = messages?.find((m: any) => m.id === messageId);
  
  // Log for debugging - more detailed logging
  console.log("UnifiedFeedbackBox initialization:", { 
    messageId, 
    hybridMetadata, 
    turnId, 
    sqlSampleId, 
    summarySampleId,
    hasHybridMetadata: !!hybridMetadata,
    modelUsed: hybridMetadata?.model_used
  });
  
  // Determine if this is an API response
  const isApiResponse = () => {
    if (!hybridMetadata || !hybridMetadata.model_used) {
      console.log("No hybridMetadata or model_used, returning false for isApiResponse");
      return false;
    }
    
    // API models typically contain "deepseek" in their name
    const model = hybridMetadata.model_used.toLowerCase();
    const isApi = model.includes("deepseek") || model.includes("api");
    console.log("isApiResponse check:", { model, isApi, includesDeepseek: model.includes("deepseek"), includesApi: model.includes("api") });
    return isApi;
  };

  // Determine if this is a local response
  const isLocalResponse = () => {
    if (!hybridMetadata || !hybridMetadata.model_used) {
      console.log("No hybridMetadata or model_used, returning true for isLocalResponse (default)");
      return true; // Default to local for non-hybrid responses
    }
    
    // Local models typically contain "local", "ollama", "llama", or "mistral" in their name
    const model = hybridMetadata.model_used.toLowerCase();
    const isLocal = model.includes("local") || model.includes("ollama") || model.includes("llama") || model.includes("mistral");
    console.log("isLocalResponse check:", { model, isLocal, includesLocal: model.includes("local"), includesOllama: model.includes("ollama"), includesLlama: model.includes("llama"), includesMistral: model.includes("mistral") });
    return isLocal;
  };

  // Determine the source of the response
  const getSource = () => {
    const isApi = isApiResponse();
    const isLocal = isLocalResponse();
    const source = isApi ? "api" : (isLocal ? "local" : "");
    console.log("Determined source:", { source, isApi, isLocal, hybridMetadata });
    return source;
  };

  const [isExpanded, setIsExpanded] = useState(false);
  const [rating, setRating] = useState<"good" | "wrong" | "needs_improvement" | null>(null);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [posting, setPosting] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(false);

  // Auto-select task_type
  const pickTaskType = (): "summary" | "sql" | "overall" => {
    if (summarySampleId) return "summary";
    if (sqlSampleId) return "sql";
    return "overall";
  };

  const sendFeedback = async (
    feedbackType: "good" | "wrong" | "needs_improvement",
    improvementComment?: string
  ) => {
    if (!turnId) {
      console.log("No turnId, cannot send feedback");
      return;
    }
    
    setPosting(true);
    try {
      // Send feedback to the standard feedback endpoint
      const taskType = pickTaskType();
      const source = getSource();
      
      console.log("Preparing to send feedback with data:", {
        turn_id: turnId,
        task_type: taskType,
        feedback_type: feedbackType,
        labeler_role: "end_user",
        source: source,
        sql_sample_id: sqlSampleId,
        summary_sample_id: summarySampleId,
        comment: improvementComment
      });
      
      const body: any = {
        turn_id: turnId,
        task_type: taskType,
        feedback_type: feedbackType,
        labeler_role: "end_user",
        source: source // Add source information
      };
      
      // Add new chat_id and message_id if available
      if (chatId !== undefined && chatId !== null) body.chat_id = chatId;
      if (messageIdForFeedback !== undefined && messageIdForFeedback !== null) body.message_id = messageIdForFeedback;
      
      if (taskType === "sql") body.sql_sample_id = sqlSampleId;
      if (taskType === "summary") body.summary_sample_id = summarySampleId;
      if (feedbackType === "needs_improvement") {
        body.comment = improvementComment ?? "";
      }

      console.log("Sending feedback request:", { 
        url: "/api/feedback", 
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });


      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      
      console.log("Feedback response:", response.status, response.statusText);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const responseData = await response.json();
      console.log("Feedback response data:", responseData);
      
      setSubmitted(true);
      setFeedbackGiven(true);
      // Auto-hide after 2 seconds
      setTimeout(() => {
        setSubmitted(false);
      }, 2000);
    } catch (e) {
      console.error("Feedback submit failed:", e);
      setSubmitted(true);
      setFeedbackGiven(true);
      // Show error message for a bit longer
      setTimeout(() => {
        setSubmitted(false);
      }, 3000);
    } finally {
      setPosting(false);
    }
  };

  const handleQuickFeedback = (type: "good" | "wrong") => {
    setRating(type);
    void sendFeedback(type);
  };

  const handleSubmit = () => {
    if (!comment.trim()) return;
    setRating("needs_improvement");
    void sendFeedback("needs_improvement", comment.trim());
  };

  // 🔹 Early exits
  // Use either the old turnId or the new chatId/messageIdForFeedback
  if ((!turnId && (!chatId || !messageIdForFeedback)) || feedbackGiven) return null;

  return (
    <div className="flex justify-center">
      <AnimatePresence>
        {submitted ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className="bg-green-50 border border-green-200 rounded-lg p-3"
          >
            <div className="flex items-center gap-2 text-green-700">
              <span className="text-sm font-medium">Thank you for your feedback!</span>
            </div>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.3 }}
            className="bg-white/90 border border-gray-200 shadow rounded-lg overflow-hidden"
          >
            {/* Header */}
            <div 
              className="px-3 py-2 cursor-pointer hover:bg-gray-100 transition-colors transition-smooth smooth-hover hover-lift"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-800 text-sm">
                    Was this response helpful?
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  {!isExpanded && (
                    <>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleQuickFeedback("good");
                        }}
                        className="p-1 rounded hover:bg-gray-200 transition-colors smooth-hover hover-lift button-press"
                        title="Good"
                      >
                        <ThumbsUp size={14} className="text-green-600" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setRating("wrong");
                          setIsExpanded(true);
                        }}
                        className="p-1 rounded hover:bg-gray-200 transition-colors smooth-hover hover-lift button-press"
                        title="Needs improvement"
                      >
                        <ThumbsDown size={14} className="text-red-600" />
                      </button>
                    </>
                  )}
                  <MessageSquare size={12} className="text-gray-600" />
                </div>
              </div>
            </div>

            {/* Expanded Feedback Form */}
            <AnimatePresence>
              {isExpanded && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3 }}
                  className="px-3 pb-3 border-t border-gray-200 bg-gray-50"
                >
                  <div className="space-y-3 mt-3">
                    {/* Quote */}
                    <div className="text-center text-xs text-gray-600 italic">
                      Smart systems get smarter with smarter feedback
                    </div>
                    
                    {/* Overall Rating */}
                    <div>
                      <label className="text-xs font-medium text-gray-700 mb-1 block">
                        Overall Rating:
                      </label>
                      <div className="flex gap-2">
                        {(["good", "wrong", "needs_improvement"] as const).map((r) => (
                          <button
                            key={r}
                            onClick={() => setRating(r)}
                            className={`px-2 py-1 rounded text-xs font-medium transition-colors transition-smooth ${
                              rating === r 
                                ? "bg-primary-purple-600 text-white" 
                                : "bg-white border border-gray-300 text-gray-700 hover:bg-gray-100"
                            } smooth-hover hover-lift button-press`}
                          >
                            {r === "good" ? "👍 Good" : r === "wrong" ? "👎 Wrong" : "🛠 Needs update"}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Comment */}
                    <div>
                      <label className="text-xs font-medium text-gray-700 mb-1 block">
                        Additional feedback (optional):
                      </label>
                      <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="What should be improved?"
                        className="w-full px-2 py-1 text-xs border border-gray-300 rounded resize-none transition-smooth"
                        rows={2}
                        disabled={posting}
                      />
                    </div>

                    {/* Submit Button */}
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => {
                          setIsExpanded(false);
                          setComment("");
                        }}
                        className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800 transition-colors transition-smooth smooth-hover hover-lift button-press"
                        disabled={posting}
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSubmit}
                        disabled={posting || !comment.trim()}
                        className="px-3 py-1 text-xs bg-primary-purple-600 text-white rounded hover:bg-primary-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors transition-smooth smooth-hover hover-lift button-press"
                      >
                        {posting ? "Submitting..." : "Submit Feedback"}
                      </button>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default UnifiedFeedbackBox;