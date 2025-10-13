// src/components/HybridFeedbackBox.tsx
import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ThumbsUp, ThumbsDown, Star, Brain, MessageSquare } from "lucide-react";

type HybridMetadata = {
  processing_mode?: string;
  model_used?: string;
  selection_reasoning?: string;
  processing_time?: number;
  local_confidence?: number;
  api_confidence?: number;
};

interface Props {
  hybridMetadata?: HybridMetadata;
  onFeedback: (feedback: {
    rating: "excellent" | "good" | "fair" | "poor";
    modelPreference?: "local" | "api" | "hybrid";
    comment?: string;
    hybridSpecific?: {
      selectionCorrect: boolean;
      processingSpeed: "fast" | "medium" | "slow";
      confidenceAccurate: boolean;
    };
  }) => void;
}

const HybridFeedbackBox: React.FC<Props> = ({ hybridMetadata, onFeedback }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [rating, setRating] = useState<"excellent" | "good" | "fair" | "poor" | null>(null);
  const [modelPreference, setModelPreference] = useState<"local" | "api" | "hybrid" | null>(null);
  const [comment, setComment] = useState("");
  const [hybridSpecific, setHybridSpecific] = useState({
    selectionCorrect: true,
    processingSpeed: "fast" as "fast" | "medium" | "slow",
    confidenceAccurate: true,
  });
  const [submitted, setSubmitted] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(false); // New state to track if feedback was given

  const handleSubmit = () => {
    if (!rating) return;
    
    onFeedback({
      rating,
      modelPreference: modelPreference || undefined,
      comment: comment.trim() || undefined,
      hybridSpecific: hybridMetadata ? hybridSpecific : undefined,
    });
    
    setSubmitted(true);
    setFeedbackGiven(true); // Mark that feedback was given
    // Auto-hide after 2 seconds
    setTimeout(() => {
      setSubmitted(false);
    }, 2000);
  };

  // Handle quick feedback (excellent/poor buttons)
  const handleQuickFeedback = (rating: "excellent" | "poor") => {
    setRating(rating);
    onFeedback({ rating });
    setSubmitted(true);
    setFeedbackGiven(true); // Mark that feedback was given
    // Auto-hide after 2 seconds
    setTimeout(() => {
      setSubmitted(false);
    }, 2000);
  };

  if (!hybridMetadata || feedbackGiven) {
    return null; // Only show for hybrid responses and hide if feedback was given
  }

  return (
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
            <ThumbsUp size={16} />
            <span className="text-sm font-medium">Thank you for your feedback on the hybrid AI response!</span>
          </div>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.3 }}
          className="bg-amber-50 border border-amber-200 rounded-lg overflow-hidden"
        >
          {/* Header */}
          <div 
            className="px-3 py-2 cursor-pointer hover:bg-amber-100 transition-colors transition-smooth smooth-hover hover-lift"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain size={14} className="text-amber-600" />
                <span className="text-amber-800 font-medium text-sm">
                  How was this hybrid AI response?
                </span>
              </div>
              <div className="flex items-center gap-1">
                {!isExpanded && (
                  <>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleQuickFeedback("excellent");
                      }}
                      className="p-1 rounded hover:bg-amber-200 transition-colors smooth-hover hover-lift button-press"
                      title="Excellent"
                    >
                      <ThumbsUp size={14} className="text-green-600" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRating("poor");
                        setIsExpanded(true);
                      }}
                      className="p-1 rounded hover:bg-amber-200 transition-colors smooth-hover hover-lift button-press"
                      title="Needs improvement"
                    >
                      <ThumbsDown size={14} className="text-red-600" />
                    </button>
                  </>
                )}
                <MessageSquare size={12} className="text-amber-600" />
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
                className="px-3 pb-3 border-t border-amber-200 bg-amber-25"
              >
                <div className="space-y-3 mt-3">
                  {/* Overall Rating */}
                  <div>
                    <label className="text-xs font-medium text-gray-700 mb-1 block">
                      Overall Rating:
                    </label>
                    <div className="flex gap-2">
                      {(["excellent", "good", "fair", "poor"] as const).map((r) => (
                        <button
                          key={r}
                          onClick={() => setRating(r)}
                          className={`px-2 py-1 rounded text-xs font-medium transition-colors transition-smooth ${rating === r ? "bg-primary-purple-600 text-white" : "bg-white border border-amber-300 text-amber-700 hover:bg-amber-100"} smooth-hover hover-lift button-press`}
                        >
                          {r.charAt(0).toUpperCase() + r.slice(1)}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Model Preference */}
                  <div>
                    <label className="text-xs font-medium text-gray-700 mb-1 block">
                      Which approach do you prefer?
                    </label>
                    <div className="flex gap-2">
                      {(["local", "api", "hybrid"] as const).map((pref) => (
                        <button
                          key={pref}
                          onClick={() => setModelPreference(pref)}
                          className={`px-2 py-1 rounded text-xs font-medium transition-colors transition-smooth ${modelPreference === pref ? "bg-primary-purple-600 text-white" : "bg-white border border-blue-300 text-blue-700 hover:bg-blue-100"} smooth-hover hover-lift button-press`}
                        >
                          {pref === "local" ? "Local Only" : pref === "api" ? "API Only" : "Hybrid AI"}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Hybrid-Specific Questions */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-600">Model selection was correct:</span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => setHybridSpecific(prev => ({ ...prev, selectionCorrect: true }))}
                          className={`px-2 py-1 rounded text-xs transition-smooth ${hybridSpecific.selectionCorrect ? "bg-primary-purple-600 text-white" : "bg-gray-200 text-gray-600"} smooth-hover hover-lift button-press`}
                        >
                          Yes
                        </button>
                        <button
                          onClick={() => setHybridSpecific(prev => ({ ...prev, selectionCorrect: false }))}
                          className={`px-2 py-1 rounded text-xs transition-smooth ${!hybridSpecific.selectionCorrect ? "bg-primary-purple-600 text-white" : "bg-gray-200 text-gray-600"} smooth-hover hover-lift button-press`}
                        >
                          No
                        </button>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-600">Processing speed:</span>
                      <div className="flex gap-1">
                        {(["fast", "medium", "slow"] as const).map((speed) => (
                          <button
                            key={speed}
                            onClick={() => setHybridSpecific(prev => ({ ...prev, processingSpeed: speed }))}
                            className={`px-2 py-1 rounded text-xs transition-smooth ${hybridSpecific.processingSpeed === speed ? "bg-primary-purple-600 text-white" : "bg-gray-200 text-gray-600"} smooth-hover hover-lift button-press`}
                          >
                            {speed.charAt(0).toUpperCase() + speed.slice(1)}
                          </button>
                        ))}
                      </div>
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
                      placeholder="What could be improved about the hybrid AI system?"
                      className="w-full px-2 py-1 text-xs border border-amber-300 rounded resize-none transition-smooth"
                      rows={2}
                    />
                  </div>

                  {/* Submit Button */}
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setIsExpanded(false);
                      }}
                      className="px-3 py-1 text-xs text-gray-600 hover:text-gray-800 transition-colors transition-smooth smooth-hover hover-lift button-press"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSubmit}
                      disabled={!rating}
                      className="px-3 py-1 text-xs bg-primary-purple-600 text-white rounded hover:bg-primary-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors transition-smooth smooth-hover hover-lift button-press"
                    >
                      Submit Feedback
                    </button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default HybridFeedbackBox;