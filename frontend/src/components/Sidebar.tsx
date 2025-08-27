import { useChat } from "./ChatContext";
import { useState } from "react";
import clsx from "clsx"; // ← Make sure clsx is installed

export default function Sidebar() {
  const { clearMessages, selectedDB, setSelectedDB } = useChat();

  const handleDBSelect = (db: string) => {
    setSelectedDB(db);
  };

  return (
    <aside className="group w-[260px] h-screen bg-white/20 backdrop-blur-sm shadow-none hover:backdrop-blur-xl hover:shadow-xl border-r border-white/30 p-4 flex flex-col transition-all duration-700 ease-in-out">
      <button
        onClick={clearMessages}
        className="w-full bg-white/60 border border-white/40 py-2 rounded-xl text-sm font-semibold text-gray-800 shadow transition-all duration-300 ease-in-out
          hover:bg-[#3b0764] hover:text-white hover:shadow-lg"
      >
        New chat
      </button>

      <div className="mt-6 text-sm font-semibold text-gray-600">Chat history</div>

      <ul className="mt-2 space-y-2 text-sm text-gray-800 font-medium">
        <li className="px-3 py-1.5 rounded-lg bg-white/90 border border-blue-100 text-blue-900 shadow font-semibold">
          Chat history
        </li>
        <li className="hover:bg-white/60 hover:shadow px-3 py-1.5 rounded-lg transition duration-300 cursor-pointer">
          Sales Overview
        </li>
        <li className="hover:bg-white/60 hover:shadow px-3 py-1.5 rounded-lg transition duration-300 cursor-pointer">
          What is Challan update
        </li>
        <li className="hover:bg-white/60 hover:shadow px-3 py-1.5 rounded-lg transition duration-300 cursor-pointer">
          History essay
        </li>
      </ul>

      {/* 🔹 DB SELECTOR */}
      <div className="mt-8">
        <div className="text-sm font-semibold text-gray-600 mb-2">Choose Source DB</div>
        <div className="flex flex-col gap-2">
          <button
            onClick={() => handleDBSelect("source_db_1")}
            className={clsx(
              "py-2 rounded-lg text-sm font-semibold border shadow transition-all duration-300 ease-in-out",
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
              "py-2 rounded-lg text-sm font-semibold border shadow transition-all duration-300 ease-in-out",
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
  );
}
