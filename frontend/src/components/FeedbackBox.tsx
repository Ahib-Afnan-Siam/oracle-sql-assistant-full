// src/components/FeedbackBox.tsx
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useChat } from "./ChatContext";

const FeedbackBox = ({ messageId }: { messageId?: string }) => {
  const { lastIds } = useChat();
  const turnId = lastIds?.turn_id;
  const sqlSampleId = lastIds?.sql_sample_id ?? null;
  const summarySampleId = lastIds?.sql_summary_id ?? null;

  const [submitted, setSubmitted] = useState(false);
  const [mode, setMode] = useState<"idle" | "improve">("idle");
  const [comment, setComment] = useState("");
  const [posting, setPosting] = useState(false);
  const [feedbackGiven, setFeedbackGiven] = useState(false); // New state to track if feedback was given

  // Auto-select task_type without changing your UI
  const pickTaskType = (): "summary" | "sql" | "overall" => {
    if (summarySampleId) return "summary";
    if (sqlSampleId) return "sql";
    return "overall";
  };

  const sendFeedback = async (
    feedbackType: "good" | "wrong" | "needs_improvement",
    improvementComment?: string
  ) => {
    if (!turnId) return;
    const taskType = pickTaskType();
    const body: any = {
      turn_id: turnId,
      task_type: taskType,
      feedback_type: feedbackType,
      labeler_role: "end_user",
    };
    if (taskType === "sql") body.sql_sample_id = sqlSampleId;
    if (taskType === "summary") body.summary_sample_id = summarySampleId;
    if (feedbackType === "needs_improvement") {
      body.comment = improvementComment ?? "";
    }

    setPosting(true);
    try {
      const response = await fetch("http://localhost:8090/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      setSubmitted(true);
      setFeedbackGiven(true); // Mark that feedback was given
      // Auto-hide after 2 seconds
      setTimeout(() => {
        setSubmitted(false);
      }, 2000);
    } catch (e) {
      console.error("Feedback submit failed:", e);
      setSubmitted(true);
      setFeedbackGiven(true); // Mark that feedback was given even on error
      // Show error message for a bit longer
      setTimeout(() => {
        setSubmitted(false);
      }, 3000);
    } finally {
      setPosting(false);
    }
  };

  const handleQuick = (type: "good" | "wrong") => {
    void sendFeedback(type);
  };

  const handleImproveClick = () => {
    setMode("improve");
  };

  const handleImproveSubmit = () => {
    if (!comment.trim()) return;
    void sendFeedback("needs_improvement", comment.trim());
  };

  // 🔹 Early exits
  if (!turnId || feedbackGiven) return null; // Don't show anything if feedback was given

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
            className="bg-white/90 px-6 py-4 rounded-xl border border-gray-200 shadow text-sm text-gray-800 max-w-md w-full text-center"
          >
            <p className="font-medium mb-3">Was this response helpful?</p>

            <div className="flex justify-center gap-3">
              <button
                onClick={() => handleQuick("good")}
                disabled={posting || !turnId}
                className={`px-3 py-1 rounded-full bg-green-100 hover:bg-green-200 text-green-800 text-xs font-semibold transition ${posting || !turnId ? "opacity-60 cursor-not-allowed" : ""} smooth-hover hover-lift button-press`}
                title={!turnId ? "Please wait for the response to finish" : "Submit good feedback"}
              >
                👍 Good
              </button>

              <button
                onClick={() => handleQuick("wrong")}
                disabled={posting || !turnId}
                className={`px-3 py-1 rounded-full bg-red-100 hover:bg-red-200 text-red-800 text-xs font-semibold transition ${posting || !turnId ? "opacity-60 cursor-not-allowed" : ""} smooth-hover hover-lift button-press`}
                title={!turnId ? "Please wait for the response to finish" : "Submit wrong feedback"}
              >
                👎 Wrong
              </button>

              <button
                onClick={handleImproveClick}
                disabled={posting || !turnId}
                className={`px-3 py-1 rounded-full bg-yellow-100 hover:bg-yellow-200 text-yellow-800 text-xs font-semibold transition ${posting || !turnId ? "opacity-60 cursor-not-allowed" : ""} smooth-hover hover-lift button-press`}
                title={!turnId ? "Please wait for the response to finish" : "Suggest improvements"}
              >
                🛠 Needs update
              </button>
            </div>

            <AnimatePresence>
              {mode === "improve" && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3 }}
                  className="mt-3 text-left"
                >
                  <textarea
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="What should be improved?"
                    className="w-full border rounded p-2 text-sm transition-smooth"
                    rows={3}
                    disabled={posting}
                  />
                  <div className="mt-2 flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setMode("idle");
                        setComment("");
                      }}
                      disabled={posting}
                      className={`px-4 py-1.5 rounded-lg text-sm font-semibold ${posting ? "bg-gray-200 text-gray-500 cursor-not-allowed" : "bg-gray-200 text-gray-700 hover:bg-gray-300 smooth-hover hover-lift"} button-press`}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleImproveSubmit}
                      disabled={posting || !comment.trim()}
                      className={`px-4 py-1.5 rounded-lg text-sm font-semibold ${posting || !comment.trim() ? "bg-gray-200 text-gray-500 cursor-not-allowed" : "bg-purple-600 text-white hover:bg-purple-700 smooth-hover hover-lift"} button-press`}
                    >
                      {posting ? "Submitting..." : "Submit"}
                    </button>
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

export default FeedbackBox;