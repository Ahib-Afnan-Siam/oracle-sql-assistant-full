// src/components/Sidebar.tsx
import { useChat } from "./ChatContext";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { PanelLeftClose, PanelLeftOpen, Info } from "lucide-react";
import { getPrompts } from "../utils/prompts";
import ChatHistory from "./ChatHistory";

// Define mode information with descriptions and colors
const MODE_INFO = {
  "SOS": {
    icon: "🧠",
    description: "Standard business queries for SOS data",
    color: "bg-blue-500",
    bgColor: "bg-blue-500/20",
    borderColor: "border-blue-500",
    hoverColor: "hover:bg-blue-500"
  },
  "General": {
    icon: "🌐",
    description: "General knowledge and non-database questions",
    color: "bg-green-500",
    bgColor: "bg-green-500/20",
    borderColor: "border-green-500",
    hoverColor: "hover:bg-green-500"
  },
  "PRAN ERP": {
    icon: "🏢",
    description: "Ask about Inventory & Supply Chain of PRAN",
    color: "bg-purple-500",
    bgColor: "bg-purple-500/20",
    borderColor: "border-purple-500",
    hoverColor: "hover:bg-purple-500"
  },
  "RFL ERP": {
    icon: "🏭",
    description: "Ask about Inventory & Supply Chain of RFL",
    color: "bg-indigo-500",
    bgColor: "bg-indigo-500/20",
    borderColor: "border-indigo-500",
    hoverColor: "hover:bg-indigo-500"
  }
};

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
  const [modeUsage, setModeUsage] = useState<Record<string, number>>({});
  const [showModeInfo, setShowModeInfo] = useState<string | null>(null);

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

  // Load mode usage from localStorage on component mount
  useEffect(() => {
    const savedUsage = localStorage.getItem('modeUsage');
    if (savedUsage) {
      try {
        setModeUsage(JSON.parse(savedUsage));
      } catch (e) {
        console.warn('Failed to parse mode usage data', e);
      }
    }
  }, []);

  // Update mode usage when mode changes
  useEffect(() => {
    if (mode) {
      setModeUsage(prev => {
        const newUsage = {
          ...prev,
          [mode]: (prev[mode] || 0) + 1
        };
        // Save to localStorage
        localStorage.setItem('modeUsage', JSON.stringify(newUsage));
        return newUsage;
      });
    }
  }, [mode]);

  const toggleSidebar = () => setIsOpen((s) => !s);

  // Mode switch - updated parameter order
  const handleModeSelect = (newMode: "SOS" | "General" | "PRAN ERP" | "RFL ERP") => {
    setMode(newMode);
    if (newMode === "General") setSelectedDB("");
    else if (newMode === "SOS") setSelectedDB("source_db_1");
    else if (newMode === "PRAN ERP") setSelectedDB("source_db_2");
    else setSelectedDB("source_db_3");
    setIsModeDropdownOpen(false); // Close dropdown after selection
  };

  // Prompts per mode
  const promptsKey =
    mode === "SOS" ? "source_db_1" : mode === "PRAN ERP" ? "source_db_2" : mode === "RFL ERP" ? "source_db_3" : "general";
  const prompts = useMemo(() => getPrompts(promptsKey) ?? [], [promptsKey]);

  // Get most used mode
  const mostUsedMode = useMemo(() => {
    const entries = Object.entries(modeUsage);
    if (entries.length === 0) return null;
    return entries.reduce((a, b) => a[1] > b[1] ? a : b)[0];
  }, [modeUsage]);

  const railBase =
    "h-[100dvh] min-h-0 bg-white/20 backdrop-blur-sm border-r border-white/30 flex flex-col dark:bg-gray-800/20 dark:border-gray-700/30";

  return (
    <>
      {/* Mode Selection Dropdown - Glassy Sidebar with Animations */}
      {isModeDropdownOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div 
            className="absolute inset-0 bg-black/20 backdrop-blur-sm transition-opacity duration-200 ease-in-out dark:bg-black/40"
            onClick={() => setIsModeDropdownOpen(false)}
          />
          <div className="relative h-full w-full sm:w-80 bg-white/90 backdrop-blur-xl border-l border-white/40 shadow-2xl z-50 transform transition-transform duration-300 ease-out-expo slide-in-right dark:bg-gray-800/90 dark:border-gray-700/40">
            <div className="p-4 sm:p-6">
              <h2 className="text-lg sm:text-xl font-bold text-gray-800 mb-4 sm:mb-6 animate-fadeIn-subtle dark:text-gray-100">Select Mode</h2>
              <div className="space-y-3">
                {/* General is now the first option */}
                <button
                  onClick={() => handleModeSelect("General")}
                  className={clsx(
                    "w-full py-2 sm:py-2 rounded-xl text-sm sm:text-base font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-3 transform transition-transform hover:scale-[1.01] mode-button-1-subtle smooth-hover hover-lift relative",
                    mode === "General"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md dark:bg-gray-700/70 dark:text-gray-100 dark:border-gray-600/50 dark:hover:bg-primary-purple-600"
                  )}
                  onMouseEnter={() => setShowModeInfo("General")}
                  onMouseLeave={() => setShowModeInfo(null)}
                >
                  <span className="mr-2 text-lg">🌐</span>
                  <div className="flex flex-col items-start">
                    <div className="flex items-center">
                      <span className="text-left">General</span>
                      {mostUsedMode === "General" && (
                        <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full dark:bg-yellow-900/30 dark:text-yellow-200">
                          Most Used
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-left opacity-80">
                      {MODE_INFO.General.description}
                    </span>
                  </div>
                  <Info className="ml-auto h-4 w-4 opacity-50" />
                  {showModeInfo === "General" && (
                    <div className="absolute left-full ml-2 top-0 w-64 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <div className="font-semibold mb-1">General Mode</div>
                      <p className="text-sm text-gray-600 dark:text-gray-300">
                        {MODE_INFO.General.description}
                      </p>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        Best for: General knowledge questions, explanations, non-database queries
                      </div>
                    </div>
                  )}
                </button>
                <button
                  onClick={() => handleModeSelect("PRAN ERP")}
                  className={clsx(
                    "w-full py-2 sm:py-2 rounded-xl text-sm sm:text-base font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-3 transform transition-transform hover:scale-[1.01] mode-button-2-subtle smooth-hover hover-lift relative",
                    mode === "PRAN ERP"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md dark:bg-gray-700/70 dark:text-gray-100 dark:border-gray-600/50 dark:hover:bg-primary-purple-600"
                  )}
                  onMouseEnter={() => setShowModeInfo("PRAN ERP")}
                  onMouseLeave={() => setShowModeInfo(null)}
                >
                  <span className="mr-2 text-lg">🏢</span>
                  <div className="flex flex-col items-start">
                    <div className="flex items-center">
                      <span className="text-left">PRAN ERP</span>
                      {mostUsedMode === "PRAN ERP" && (
                        <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full dark:bg-yellow-900/30 dark:text-yellow-200">
                          Most Used
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-left opacity-80">
                      {MODE_INFO["PRAN ERP"].description}
                    </span>
                  </div>
                  <Info className="ml-auto h-4 w-4 opacity-50" />
                  {showModeInfo === "PRAN ERP" && (
                    <div className="absolute left-full ml-2 top-0 w-64 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <div className="font-semibold mb-1">PRAN ERP Mode</div>
                      <p className="text-sm text-gray-600 dark:text-gray-300">
                        {MODE_INFO["PRAN ERP"].description}
                      </p>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        Best for: Ask about Inventory & Supply Chain of PRAN
                      </div>
                    </div>
                  )}
                </button>
                <button
                  onClick={() => handleModeSelect("RFL ERP")}
                  className={clsx(
                    "w-full py-2 sm:py-2 rounded-xl text-sm sm:text-base font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-3 transform transition-transform hover:scale-[1.01] mode-button-3-subtle smooth-hover hover-lift relative",
                    mode === "RFL ERP"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md dark:bg-gray-700/70 dark:text-gray-100 dark:border-gray-600/50 dark:hover:bg-primary-purple-600"
                  )}
                  onMouseEnter={() => setShowModeInfo("RFL ERP")}
                  onMouseLeave={() => setShowModeInfo(null)}
                >
                  <span className="mr-2 text-lg">🏭</span>
                  <div className="flex flex-col items-start">
                    <div className="flex items-center">
                      <span className="text-left">RFL ERP</span>
                      {mostUsedMode === "RFL ERP" && (
                        <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full dark:bg-yellow-900/30 dark:text-yellow-200">
                          Most Used
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-left opacity-80">
                      {MODE_INFO["RFL ERP"].description}
                    </span>
                  </div>
                  <Info className="ml-auto h-4 w-4 opacity-50" />
                  {showModeInfo === "RFL ERP" && (
                    <div className="absolute left-full ml-2 top-0 w-64 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <div className="font-semibold mb-1">RFL ERP Mode</div>
                      <p className="text-sm text-gray-600 dark:text-gray-300">
                        {MODE_INFO["RFL ERP"].description}
                      </p>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        Best for: Ask about Inventory & Supply Chain of RFL
                      </div>
                    </div>
                  )}
                </button>
                {/* SOS is now the fourth option */}
                <button
                  onClick={() => handleModeSelect("SOS")}
                  className={clsx(
                    "w-full py-2 sm:py-2 rounded-xl text-sm sm:text-base font-semibold border shadow-sm transition-all duration-200 flex items-center justify-start px-3 transform transition-transform hover:scale-[1.01] mode-button-4-subtle smooth-hover hover-lift relative",
                    mode === "SOS"
                      ? "bg-primary-purple-600 text-white border-primary-purple-600 shadow-md"
                      : "bg-white/70 text-gray-800 border-white/50 hover:bg-primary-purple-600 hover:text-white hover:shadow-md dark:bg-gray-700/70 dark:text-gray-100 dark:border-gray-600/50 dark:hover:bg-primary-purple-600"
                  )}
                  onMouseEnter={() => setShowModeInfo("SOS")}
                  onMouseLeave={() => setShowModeInfo(null)}
                >
                  <span className="mr-2 text-lg">🧠</span>
                  <div className="flex flex-col items-start">
                    <div className="flex items-center">
                      <span className="text-left">SOS</span>
                      {mostUsedMode === "SOS" && (
                        <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full dark:bg-yellow-900/30 dark:text-yellow-200">
                          Most Used
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-left opacity-80">
                      {MODE_INFO.SOS.description}
                    </span>
                  </div>
                  <Info className="ml-auto h-4 w-4 opacity-50" />
                  {showModeInfo === "SOS" && (
                    <div className="absolute left-full ml-2 top-0 w-64 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <div className="font-semibold mb-1">SOS Mode</div>
                      <p className="text-sm text-gray-600 dark:text-gray-300">
                        {MODE_INFO.SOS.description}
                      </p>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        Best for: Operational data queries, business metrics, performance analysis
                      </div>
                    </div>
                  )}
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
          className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm transition-opacity duration-300 dark:bg-black/40"
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
        <div className="flex items-center justify-between h-16 px-4 bg-white/80 backdrop-blur border-b border-white/40 dark:bg-gray-800/80 dark:border-gray-700/40">
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
              "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-primary-purple-600/40 button-press dark:border-gray-700/60 dark:bg-gray-800/95 dark:text-gray-300 dark:hover:bg-primary-purple-600 dark:hover:text-white"
            )}
          >
            {isOpen ? (
              <PanelLeftClose className="h-5 w-5" strokeWidth={2.25} />
            ) : (
              <PanelLeftOpen className="h-5 w-5" strokeWidth={2.25} />
            )}
          </button>
        </div>

        {/* Content - Fixed scrolling behavior */}
        <div
          className={clsx(
            !isMobile && !isOpen && "hidden",
            "flex flex-col flex-1 min-h-0 px-4 transition-smooth h-full"
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
              "dark:bg-gray-700/60 dark:text-gray-100 dark:border-gray-600/40 dark:hover:bg-primary-purple-600",
              isTyping && "opacity-60 cursor-not-allowed"
            )}
          >
            New chat
          </button>

          {/* Chat History Section */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <ChatHistory />
          </div>
        </div>

        {/* Mode selector - simplified to a single button that opens the dropdown */}
        <div className={clsx(!isMobile && !isOpen && "hidden", "px-4 pb-4 pt-3 transition-smooth")}>
          <div className="text-sm font-semibold text-gray-600 mb-2 transition-smooth dark:text-gray-300">Mode</div>
          <button
            onClick={() => setIsModeDropdownOpen(true)}
            className={clsx(
              "w-full py-4 rounded-lg text-base font-semibold border shadow transition-all duration-300 flex items-center justify-between px-4 transform transition-transform hover:scale-[1.01]",
              "bg-white/60 text-gray-800 border-white/40",
              "hover:bg-primary-purple-600 hover:text-white hover:shadow-md smooth-hover hover-lift button-press",
              "dark:bg-gray-700/60 dark:text-gray-100 dark:border-gray-600/40 dark:hover:bg-primary-purple-600",
              // Add active mode indicator
              mode === "SOS" && "border-blue-500",
              mode === "General" && "border-green-500",
              mode === "PRAN ERP" && "border-purple-500",
              mode === "RFL ERP" && "border-indigo-500"
            )}
          >
            <span className="flex items-center">
              {mode === "SOS" && "🧠"}
              {mode === "General" && "🌐"}
              {mode === "PRAN ERP" && "🏢"}
              {mode === "RFL ERP" && "🏭"}
              <span className="ml-2">{mode}</span>
              {mostUsedMode === mode && (
                <span className="ml-2 text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full dark:bg-yellow-900/30 dark:text-yellow-200">
                  Most Used
                </span>
              )}
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
          {/* Mode description */}
          <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 px-2">
            {MODE_INFO[mode].description}
          </div>
        </div>
      </aside>

      {/* Floating open button when closed - Fixed positioning */}
      {!isOpen && (
        <button
          onClick={toggleSidebar}
          aria-label="Open sidebar"
          title="Open sidebar"
          className={clsx(
            "fixed left-3 top-4 z-[60] inline-flex h-12 w-12 items-center justify-center rounded-full",
            "border border-white/60 bg-white/95 text-gray-700 shadow-lg transition-all duration-200 ease-out hover:shadow-xl",
            "hover:bg-primary-purple-600 hover:text-white animate-float-subtle button-press hover-scale-strong",
            "dark:border-gray-700/60 dark:bg-gray-800/95 dark:text-gray-300 dark:hover:bg-primary-purple-600 dark:hover:text-white"
          )}
        >
          <PanelLeftOpen className="h-6 w-6" strokeWidth={2.25} />
        </button>
      )}
    </>
  );
}