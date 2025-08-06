// src/components/FeedbackBox.tsx
import { useState } from "react";

const FeedbackBox = () => {
  const [submitted, setSubmitted] = useState(false);

  const handleFeedback = (type: "good" | "bad" | "improve") => {
    // 🟡 Placeholder for future backend integration
    console.log("Feedback submitted:", type);
    setSubmitted(true);
  };

  return (
    <div className="flex justify-center mt-4">
      <div className="bg-white/90 px-6 py-4 rounded-xl border border-gray-200 shadow text-sm text-gray-800 max-w-md w-full text-center">
        {!submitted ? (
          <>
            <p className="font-medium mb-3">Was this response helpful?</p>
            <div className="flex justify-center gap-3">
              <button
                onClick={() => handleFeedback("good")}
                className="px-3 py-1 rounded-full bg-green-100 hover:bg-green-200 text-green-800 text-xs font-semibold transition"
              >
                👍 Good
              </button>
              <button
                onClick={() => handleFeedback("bad")}
                className="px-3 py-1 rounded-full bg-red-100 hover:bg-red-200 text-red-800 text-xs font-semibold transition"
              >
                👎 Wrong
              </button>
              <button
                onClick={() => handleFeedback("improve")}
                className="px-3 py-1 rounded-full bg-yellow-100 hover:bg-yellow-200 text-yellow-800 text-xs font-semibold transition"
              >
                🛠 Needs update
              </button>
            </div>
          </>
        ) : (
          <p className="text-green-600 text-sm font-medium">✅ Thanks for your feedback!</p>
        )}
      </div>
    </div>
  );
};

export default FeedbackBox;
