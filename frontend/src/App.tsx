import './theme.css';
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import HomePrompts from "./components/HomePrompts";
import { useChat } from "./components/ChatContext";
import { AnimatePresence, motion } from "framer-motion";
import ChatInput from "./components/ChatInput";
import { useTheme } from './components/ThemeContext';
import { Sun, Moon } from 'lucide-react';

function App() {
  const { messages } = useChat();
  const { theme, toggleTheme } = useTheme();

  return (
    <div className="relative w-full h-screen overflow-hidden bg-background-color text-text-color">
      {/* Theme Toggle Button */}
      <button
        onClick={toggleTheme}
        className="fixed top-4 right-4 z-50 p-2 rounded-full bg-surface-color border border-border-color shadow-sm text-text-color hover:bg-primary-purple-600 hover:text-white transition-colors duration-200"
        aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
      </button>

      <div className="flex h-full w-full">
        {/* Sidebar handles its own responsive behavior (desktop rail + mobile drawer) */}
        <Sidebar />

        {/* Main area - Fixed scrolling behavior */}
        <div className="flex-1 flex flex-col bg-background-color min-h-0">
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <AnimatePresence mode="wait">
              {messages.length === 0 ? (
                <motion.div
                  key="home"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.35, ease: "easeInOut" }}
                  className="flex-1 flex items-center justify-center overflow-y-auto"
                >
                  <HomePrompts />
                </motion.div>
              ) : (
                <motion.div
                  key="chat"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.35, ease: "easeInOut" }}
                  className="flex-1 overflow-y-auto"
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