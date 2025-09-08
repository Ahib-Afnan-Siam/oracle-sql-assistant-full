import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import HomePrompts from "./components/HomePrompts";
import { useChat } from "./components/ChatContext";
import { AnimatePresence, motion } from "framer-motion";
import ChatInput from "./components/ChatInput";

function App() {
  const { messages } = useChat();

  return (
    <div className="relative w-full h-full overflow-hidden">
      <div className="flex h-full w-full">
        {/* Sidebar handles its own responsive behavior (desktop rail + mobile drawer) */}
        <Sidebar />

        {/* Main area */}
        <div className="flex-1 flex flex-col bg-transparent">
          <div className="flex-1 flex flex-col overflow-y-auto">
            <AnimatePresence mode="wait">
              {messages.length === 0 ? (
                <motion.div
                  key="home"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.35 }}
                  className="flex-1 flex items-center justify-center"
                >
                  <HomePrompts />
                </motion.div>
              ) : (
                <motion.div
                  key="chat"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.35 }}
                  className="flex-1"
                >
                  <ChatPanel />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Single input for both Home + Chat views */}
          <ChatInput />
        </div>
      </div>
    </div>
  );
}

export default App;
