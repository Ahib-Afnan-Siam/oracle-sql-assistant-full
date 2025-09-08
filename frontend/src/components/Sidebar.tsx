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
    processMessage,
    isTyping,
  } = useChat();

  const [isMobile, setIsMobile] = useState(false);
  const [isOpen, setIsOpen] = useState(true);

  useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    const sync = () => {
      const mobile = mql.matches;
      setIsMobile(mobile);
      setIsOpen(!mobile); // desktop: open, mobile: closed
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
  const handleDBSelect = (db: string) => setSelectedDB(db);
  const prompts = useMemo(() => getPrompts(selectedDB), [selectedDB]);

  const railBase =
    "h-[100dvh] min-h-0 bg-white/20 backdrop-blur-sm border-r border-white/30 flex flex-col";

  return (
    <>
      {isMobile && isOpen && (
        <button
          aria-hidden="true"
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-40 bg-black/30"
        />
      )}

      <aside
        role={isMobile ? "dialog" : undefined}
        aria-modal={isMobile ? true : undefined}
        aria-hidden={isMobile ? (!isOpen).toString() : undefined}
        className={clsx(
          railBase,
          "overflow-hidden transition-all duration-300 ease-in-out will-change-transform will-change-[width]",
          isMobile
            ? clsx(
                "fixed left-0 top-0 z-50 w-[80vw] max-w-[320px] shadow-xl",
                isOpen ? "translate-x-0" : "-translate-x-full"
              )
            : // ⬇ widen a bit on desktop
              clsx("relative z-10", isOpen ? "w-72 md:w-[300px]" : "w-0")
        )}
      >
        {/* Toggle row */}
        <div className="h-12 flex items-center justify-end px-3">
          <button
            onClick={toggleSidebar}
            aria-label={isOpen ? "Close sidebar" : "Open sidebar"}
            aria-expanded={isOpen}
            title={isOpen ? "Close sidebar" : "Open sidebar"}
            className={clsx(
              "inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/60 bg-white/95 text-gray-700 shadow",
              "transition-all duration-300 hover:shadow-lg hover:bg-[#3b0764] hover:text-white",
              "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#3b0764]/40"
            )}
          >
            {isOpen ? (
              <PanelLeftClose className="h-5 w-5" strokeWidth={2.25} />
            ) : (
              <PanelLeftOpen className="h-5 w-5" strokeWidth={2.25} />
            )}
          </button>
        </div>

        {/* Content column */}
        <div className={clsx(!isMobile && !isOpen && "hidden", "flex flex-col flex-1 min-h-0 px-4")}>
          {/* New chat */}
          <button
            onClick={clearMessages}
            disabled={isTyping}
            className={clsx(
              "w-full py-2 rounded-xl text-sm font-semibold border shadow transition-all duration-300",
              "bg-white/60 text-gray-800 border-white/40",
              "hover:bg-[#3b0764] hover:text-white hover:shadow-lg",
              isTyping && "opacity-60 cursor-not-allowed"
            )}
          >
            New chat
          </button>

          {/* Chat Menu (scrolls) */}
          <div className="mt-4 text-sm font-semibold text-gray-600">Chat Menu</div>

          <div className="mt-2 flex-1 min-h-0 overflow-y-auto pr-1 space-y-2 pb-3">
            {prompts.map((text) => (
              <button
                key={text}
                onClick={() => processMessage(text, selectedDB)}
                disabled={isTyping}
                className={clsx(
                  "w-full text-left px-3 py-2 rounded-xl border shadow-sm transition-all duration-300",
                  "bg-white/70 text-gray-800 border-white/50",
                  // ⬇ smaller font + tighter line-height, keeps the hover animation
                  "text-xs md:text-[13px] leading-snug",
                  "hover:bg-[#3b0764] hover:text-white hover:shadow-lg hover:translate-x-0.5",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3b0764]/50",
                  isTyping && "opacity-60 cursor-not-allowed"
                )}
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        {/* Pinned DB selector */}
        <div className={clsx(!isMobile && !isOpen && "hidden", "px-4 pb-4 pt-3")}>
          <div className="text-sm font-semibold text-gray-600 mb-2">Choose Source DB</div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => handleDBSelect("source_db_1")}
              className={clsx(
                "py-2 rounded-lg text-sm font-semibold border shadow transition-all duration-300",
                selectedDB === "source_db_1"
                  ? "bg-[#3b0764] text-white border-[#3b0764]"
                  : "bg-white/60 text-gray-800 border-white/40 hover:bg-white/80"
              )}
            >
              🧠 SOS
            </button>
            <button
              onClick={() => handleDBSelect("source_db_2")}
              className={clsx(
                "py-2 rounded-lg text-sm font-semibold border shadow transition-all duration-300",
                selectedDB === "source_db_2"
                  ? "bg-[#3b0764] text-white border-[#3b0764]"
                  : "bg-white/60 text-gray-800 border-white/40 hover:bg-white/80"
              )}
            >
              🏢 Test DB
            </button>
          </div>
        </div>
      </aside>

      {/* Floating open button when closed */}
      {!isOpen && (
        <button
          onClick={toggleSidebar}
          aria-label="Open sidebar"
          title="Open sidebar"
          className={clsx(
            "fixed left-3 top-4 z-[60] inline-flex h-10 w-10 items-center justify-center rounded-full",
            "border border-white/60 bg-white/95 text-gray-700 shadow transition-all duration-300",
            "hover:bg-[#3b0764] hover:text-white hover:shadow-lg"
          )}
        >
          <PanelLeftOpen className="h-5 w-5" strokeWidth={2.25} />
        </button>
      )}
    </>
  );
}
