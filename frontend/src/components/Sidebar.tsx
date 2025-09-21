// src/components/Sidebar.tsx
import { useChat } from "./ChatContext";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { getPrompts } from "../utils/prompts";

export default function Sidebar() {
  const {
    clearMessages,
    selectedDB,
    setSelectedDB,
    mode,
    setMode,
    processMessage,
    isTyping,
  } = useChat();

  const [isMobile, setIsMobile] = useState(false);
  const [isOpen, setIsOpen] = useState(true);
  const [isModeDropdownOpen, setIsModeDropdownOpen] = useState(false);

  // Responsive open/close
  useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    const sync = () => {
      const mobile = mql.matches;
      setIsMobile(mobile);
      setIsOpen(!mobile);
    };
    sync();
    mql.addEventListener("change", sync);
    return () => mql.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (isMobile) document.body.style.overflow = isOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [isMobile, isOpen]);

  const toggleSidebar = () => setIsOpen((s) => !s);

  // Mode switch - updated parameter order
  const handleModeSelect = (newMode: "SOS" | "General" | "Test DB") => {
    setMode(newMode);
    if (newMode === "General") setSelectedDB("");
    else if (newMode === "SOS") setSelectedDB("source_db_1");
    else setSelectedDB("source_db_2");
    setIsModeDropdownOpen(false); // Close dropdown after selection
  };

  // Prompts per mode
  const promptsKey =
    mode === "SOS" ? "source_db_1" : mode === "Test DB" ? "source_db_2" : "general";
  const prompts = useMemo(() => getPrompts(promptsKey) ?? [], [promptsKey]);

  const railBase =
    "h-[100dvh] min-h-0 bg-white/20 backdrop-blur-sm border-r border-white/30 flex flex-col";

  return (
    <>
      {/* Mode Selection Dropdown - Glassy Sidebar with Animations */}
      {isModeDropdownOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div 
            className="absolute inset-0 bg-black/20 backdrop-blur-sm transition-opacity duration-200 ease-in-out"
            onClick={() => setIsModeDropdownOpen(false)}
          />
          <div className="relative h-full w-full sm:w-80 bg-white/90 backdrop-blur-xl border-l border-white/40 shadow-2xl z-50 transform transition-transform duration-300 ease-out-expo slide-in-right">
            <div className="p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-bold text-gray-800 mb-4 sm:mb-6 animate-fadeIn-subtle">Select Mode</h2>
              <div className="space-y-3">
                {/* SOS is now the first option */}
                <button
                  onClick={() => handleModeSelect("SOS")}
                  className={clsx(
                    "w-full py-4 sm:py-4 rounded-xl text-base sm:text-lg font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-4 transform transition-transform hover:scale-[1.01] mode-button-1-subtle smooth-hover hover-lift",
                    mode === "SOS"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md"
                  )}
                >
                  <span className="mr-3 text-xl">🧠</span>
                  <span className="text-left">SOS</span>
                </button>
                <button
                  onClick={() => handleModeSelect("General")}
                  className={clsx(
                    "w-full py-4 sm:py-4 rounded-xl text-base sm:text-lg font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-4 transform transition-transform hover:scale-[1.01] mode-button-2-subtle smooth-hover hover-lift",
                    mode === "General"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md"
                  )}
                >
                  <span className="mr-3 text-xl">🌐</span>
                  <span className="text-left">General</span>
                </button>
                <button
                  onClick={() => handleModeSelect("Test DB")}
                  className={clsx(
                    "w-full py-4 sm:py-4 rounded-xl text-base sm:text-lg font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-4 transform transition-transform hover:scale-[1.01] mode-button-3-subtle smooth-hover hover-lift",
                    mode === "Test DB"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md"
                  )}
                >
                  <span className="mr-3 text-xl">🏢</span>
                  <span className="text-left">Test DB</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isMobile && isOpen && (
        <button
          aria-hidden
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity duration-300"
        />
      )}

      <aside
        role={isMobile ? "dialog" : undefined}
        aria-modal={isMobile || undefined}
        aria-hidden={isMobile && !isOpen ? true : undefined}
        className={clsx(
          railBase,
          "overflow-x-hidden transition-all duration-300 ease-in-out will-change-transform will-change-[width] transition-smooth",
          isMobile
            ? clsx(
                "fixed left-0 top-0 z-50 w-[85vw] max-w-[320px] shadow-xl",
                isOpen ? "translate-x-0" : "-translate-x-full"
              )
            : clsx("relative z-10", isOpen ? "w-72 md:w-[300px]" : "w-0")
        )}
      >
        {/* Header bar: logo + toggle button, positioned at the top */}
        <div className="flex items-center justify-between h-16 px-4 bg-white/80 backdrop-blur border-b border-white/40">
          <button
            onClick={clearMessages}
            disabled={isTyping}
            className="w-[140px] md:w-[160px] h-auto object-contain select-none transition-smooth focus:outline-none"
            aria-label="Start new chat"
            title="Start new chat"
          >
            <img
              src="/Uttoron%201-01.png"
              alt="Uttoron"
              className="w-full h-auto object-contain select-none"
              draggable={false}
            />
          </button>
          <button
            onClick={toggleSidebar}
            aria-label={isOpen ? "Close sidebar" : "Open sidebar"}
            aria-expanded={isOpen}
            title={isOpen ? "Close sidebar" : "Open sidebar"}
            className={clsx(
              "inline-flex h-10 w-10 items-center justify-center rounded-full",
              "border border-white/60 bg-white/95 text-gray-700 shadow",
              "transition-all duration-300 hover:shadow-lg hover:bg-primary-purple-600 hover:text-white",
              "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary-purple-600/40 button-press"
            )}
          >
            {isOpen ? (
              <PanelLeftClose className="h-5 w-5" strokeWidth={2.25} />
            ) : (
              <PanelLeftOpen className="h-5 w-5" strokeWidth={2.25} />
            )}
          </button>
        </div>

        {/* Content */}
        <div
          className={clsx(
            !isMobile && !isOpen && "hidden",
            "flex flex-col flex-1 min-h-0 px-4 transition-smooth"
          )}
        >
          {/* New chat - moved up since logo is now in header */}
          <button
            onClick={clearMessages}
            disabled={isTyping}
            className={clsx(
              "mt-4 w-full py-2 rounded-xl text-sm font-semibold border shadow transition-all duration-300",
              "bg-white/60 text-gray-800 border-white/40",
              "hover:bg-primary-purple-600 hover:text-white hover:shadow-lg smooth-hover hover-lift button-press",
              isTyping && "opacity-60 cursor-not-allowed"
            )}
          >
            New chat
          </button>

          {/* Chat Menu */}`
          <div className="mt-4 text-sm font-semibold text-gray-600 transition-smooth">Chat Menu</div>
          <div className="mt-2 flex-1 min-h-0 overflow-y-auto pr-1 space-y-2 pb-3 transition-smooth">
            {prompts.map((text, index) => (
              <button
                key={text}
                onClick={() => processMessage(text, selectedDB, mode)}
                disabled={isTyping}
                className={clsx(
                  "w-full text-left px-3 py-2 rounded-xl border shadow-sm transition-all duration-300",
                  "bg-white/70 text-gray-800 border-white/50",
                  "text-xs md:text-[13px] leading-snug",
                  "hover:bg-primary-purple-600 hover:text-white hover:shadow-lg hover:translate-x-0.5 smooth-hover hover-lift button-press",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-purple-600/50",
                  "staggered-animation animate",
                  isTyping && "opacity-60 cursor-not-allowed"
                )}
                style={{ animationDelay: `${index * 0.05}s` }}
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        {/* Mode selector - simplified to a single button that opens the dropdown */}
        <div className={clsx(!isMobile && !isOpen && "hidden", "px-4 pb-4 pt-3 transition-smooth")}>
          <div className="text-sm font-semibold text-gray-600 mb-2 transition-smooth">Mode</div>
          <button
            onClick={() => setIsModeDropdownOpen(true)}
            className={clsx(
              "w-full py-4 rounded-lg text-base font-semibold border shadow transition-all duration-300 flex items-center justify-between px-4 transform transition-transform hover:scale-[1.01]",
              "bg-white/60 text-gray-800 border-white/40",
              "hover:bg-primary-purple-600 hover:text-white hover:shadow-md smooth-hover hover-lift button-press"
            )}
          >
            <span className="flex items-center">
              {mode === "SOS" && "🧠"}
              {mode === "General" && "🌐"}
              {mode === "Test DB" && "🏢"}
              <span className="ml-2">{mode}</span>
            </span>
            <span 
              className={clsx(
                "transition-transform duration-300",
                isModeDropdownOpen ? "rotate-180" : ""
              )}
            >
              ▼
            </span>
          </button>
        </div>
      </aside>

      {/* Floating open button when closed */}
      {!isOpen && (
        <button
          onClick={toggleSidebar}
          aria-label="Open sidebar"
          title="Open sidebar"
          className={clsx(
            "fixed left-3 top-4 z-[60] inline-flex h-12 w-12 items-center justify-center rounded-full",
            "border border-white/60 bg-white/95 text-gray-700 shadow-lg transition-all duration-200 ease-out hover:shadow-xl",
            "hover:bg-primary-purple-600 hover:text-white animate-float-subtle button-press hover-scale-strong"
          )}
        >
          <PanelLeftOpen className="h-6 w-6" strokeWidth={2.25} />
        </button>
      )}
    </>
  );
}