// src/components/ChatInput.tsx
import React, { useState, useRef, useEffect } from "react";
import { PaperPlaneIcon } from "@radix-ui/react-icons";
import { Paperclip } from "lucide-react";
import { useChat } from "./ChatContext";

export default function ChatInput() {
  const [input, setInput] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    processMessage,
    processFileMessage,
    isTyping,
    isPaused,
    setIsPaused,
    selectedDB,
    mode,
  } = useChat();

  // Auto-resize textarea based on content
  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      // Limit height to 120px (about 5 lines) to prevent overflow
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  };

  // Adjust textarea height when input changes
  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  const sendNow = () => {
    const trimmed = input.trim();
    if (!trimmed || isTyping) return;

    if (selectedFile && mode === "General") {
      // Process file message only in General mode
      processFileMessage(selectedFile, trimmed, selectedDB, mode);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } else {
      processMessage(trimmed, selectedDB, mode);
    }
    setInput("");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendNow();
  };

  const handleKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter") {
      if (e.shiftKey) {
        // Shift+Enter: Allow default behavior (new line)
        return;
      } else {
        // Enter alone: Submit the form
        e.preventDefault();
        sendNow();
      }
    }
  };

  const handleStop = () => {
    if (isTyping && !isPaused) setIsPaused(true);
  };

  // ------- File handling -------
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      } else {
        alert(
          "Invalid file. Please select a file under 5MB of type: PDF, DOC, DOCX, TXT, CSV, XLSX, PNG, JPG, JPEG, or GIF."
        );
      }
    }
  };

  const validateFile = (file: File): boolean => {
    if (file.size > 5 * 1024 * 1024) return false; // 5MB
    const allowedTypes = [
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "text/plain",
      "text/csv",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "image/png",
      "image/jpeg",
      "image/gif",
    ];
    return allowedTypes.includes(file.type);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (mode === "General") setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (mode !== "General") return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      const file = files[0];
      if (validateFile(file)) {
        setSelectedFile(file);
      } else {
        alert(
          "Invalid file. Please select a file under 5MB of type: PDF, DOC, DOCX, TXT, CSV, XLSX, PNG, JPG, JPEG, or GIF."
        );
      }
    }
  };

  const removeFile = () => {
    setSelectedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const triggerFileInput = () => {
    if (fileInputRef.current && mode === "General") {
      fileInputRef.current.click();
    }
  };
  // -----------------------------

  return (
    <form
      onSubmit={handleSubmit}
      className="w-full flex justify-center px-4 pb-4 relative z-20"
    >
      <div className="w-full max-w-2xl">
        {/* Container with drag&drop support */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`flex flex-col w-full chat-input-container rounded-xl p-2 shadow-md transition-all duration-200
            ${isDragging && mode === "General" ? "ring-2 ring-blue-400 bg-blue-50/80 dark:bg-blue-900/30" : ""}
            ${isTyping ? "opacity-90" : ""}`}
        >
          {/* File chip row (above input) - Enhanced styling */}
          {selectedFile && mode === "General" && (
            <div className="flex items-center justify-between file-chip bg-blue-100/60 backdrop-blur-sm rounded-lg px-3 py-2 mb-2 border border-blue-200/50 dark:bg-blue-900/30 dark:border-blue-800/50">
              <div className="flex items-center min-w-0">
                <Paperclip className="h-4 w-4 text-blue-600 mr-2 flex-shrink-0 dark:text-blue-400" />
                <span className="text-sm text-gray-800 font-medium truncate dark:text-gray-200">
                  {selectedFile.name}
                </span>
                <span className="text-xs text-gray-600 ml-2 flex-shrink-0 dark:text-gray-400">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </div>
              <button
                type="button"
                onClick={removeFile}
                className="text-gray-500 hover:text-red-500 text-sm font-semibold ml-3 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500 rounded-full p-1 smooth-hover hover-lift dark:text-gray-400 dark:hover:text-red-400"
                aria-label="Remove file"
                title="Remove file"
              >
                ✕
              </button>
            </div>
          )}

          {/* Input row */}
          <div className="flex items-end gap-2">
            {/* Attach (General mode only) */}
            <button
              type="button"
              onClick={triggerFileInput}
              disabled={isTyping || mode !== "General"}
              aria-label="Attach file"
              title={mode === "General" ? "Attach file" : "Attachments available in General mode"}
              className={`p-2 rounded-full transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500 chat-input-button
                ${isTyping || mode !== "General"
                  ? "text-gray-400 cursor-not-allowed dark:text-gray-600"
                  : "text-gray-600 hover:bg-purple-100 hover:text-purple-600 smooth-hover hover-scale dark:text-gray-400 dark:hover:bg-purple-900/50 dark:hover:text-purple-400"}`}
            >
              <Paperclip className="h-5 w-5" />
            </button>

            {/* Hidden file input */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              disabled={isTyping || mode !== "General"}
              className="hidden"
              accept=".pdf,.doc,.docx,.txt,.csv,.xlsx,.png,.jpg,.jpeg,.gif"
            />

            {/* Text input: always grows */}
            <div className="flex-1 relative">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isTyping}
                placeholder={
                  mode === "General"
                    ? "Type a message or attach a file…"
                    : "Type a database question…"
                }
                className={`w-full px-3 py-2.5 pr-14 rounded-lg border text-sm placeholder-gray-500 focus:outline-none transition-all duration-200 resize-none overflow-y-auto focus:ring-2 focus:ring-purple-500
                  ${isTyping
                    ? "bg-gray-50 cursor-not-allowed opacity-70 dark:bg-gray-700"
                    : "bg-white/70 border-gray-300 focus:border-purple-500 shadow-inner dark:bg-gray-800/70 dark:border-gray-600 dark:text-gray-100 dark:placeholder-gray-400"}`}
                rows={1}
              />
              {/* Enhanced character counter - always visible but subtle */}
              <div className="absolute bottom-1.5 right-2 text-xs text-gray-400 dark:text-gray-500">
                <span className={input.length > 1800 ? "text-red-500 font-medium dark:text-red-400" : ""}>
                  {input.length}
                </span>
                <span className="text-gray-300 dark:text-gray-600">/</span>
                <span className="text-gray-500 dark:text-gray-400">2000</span>
              </div>
            </div>

            {/* Send */}
            <button
              type="submit"
              disabled={isTyping || input.trim().length === 0}
              aria-label="Send"
              title="Send"
              className={`p-2.5 rounded-full flex items-center justify-center transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500 chat-input-send-button
                ${(isTyping || input.trim().length === 0)
                  ? "opacity-50 cursor-not-allowed"
                  : "text-white shadow-md hover-scale-strong"}`}
            >
              <PaperPlaneIcon className="h-5 w-5" />
            </button>

            {/* Stop button for larger screens - hidden on mobile */}
            <button
              type="button"
              onClick={handleStop}
              disabled={!isTyping}
              className={`px-3 py-2.5 rounded-lg text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 chat-input-stop-button hidden sm:block
                ${isTyping
                  ? "text-white shadow-sm hover-scale"
                  : "opacity-50 cursor-not-allowed text-white"}`}
              aria-label="Stop"
              title="Stop"
            >
              Stop
            </button>
          </div>

          {/* Stop button visible only on small screens (mobile) and only when typing */}
          {isTyping && (
            <div className="mt-2 sm:hidden animate-fadeIn">
              <button
                type="button"
                onClick={handleStop}
                className={`w-full px-3 py-2.5 rounded-lg text-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-red-500 chat-input-stop-button text-white shadow-sm hover-scale`}
                aria-label="Stop"
                title="Stop"
              >
                Stop
              </button>
            </div>
          )}
        </div>
      </div>
    </form>
  );
}