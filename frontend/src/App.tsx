import './theme.css';
import Sidebar from "./components/Sidebar";
import ChatPanel from "./components/ChatPanel";
import HomePrompts from "./components/HomePrompts";
import { useChat } from "./components/ChatContext";
import { AnimatePresence, motion } from "framer-motion";
import ChatInput from "./components/ChatInput";
import { useTheme } from './components/ThemeContext';
import { Sun, Moon, LogOut, Shield } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';

function App() {
  const { messages } = useChat();
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const [isAdmin, setIsAdmin] = useState(false);

  // Check if user is admin on component mount
  useEffect(() => {
    const adminStatus = localStorage.getItem("isAdmin") === "true";
    setIsAdmin(adminStatus);
  }, []);

  // Handle logout
  const handleLogout = async () => {
    try {
      const token = localStorage.getItem("authToken");
      // Only call logout endpoint for non-admin users
      if (localStorage.getItem("isAdmin") !== "true") {
        await fetch("/api/logout", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`
          }
        });
      }
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      localStorage.removeItem("authToken");
      localStorage.removeItem("isAdmin");
      window.location.href = "/login";
    }
  };

  // Handle admin dashboard navigation
  const handleAdminDashboard = () => {
    navigate("/admin");
  };

  return (
    <div className="relative w-full h-screen overflow-hidden bg-background-color text-text-color">
      <div className="flex h-full w-full">
        {/* Sidebar handles its own responsive behavior (desktop rail + mobile drawer) */}
        <Sidebar />

        {/* Main area - Fixed scrolling behavior */}
        <div className="flex-1 flex flex-col bg-background-color min-h-0">
          {/* Header for chat panel only */}
          <header className="bg-surface-color p-4 flex justify-end items-center border-b border-border-color">
            <div className="flex items-center space-x-4">
              {/* Admin Dashboard Button - Only visible to admins */}
              {isAdmin && (
                <button 
                  onClick={handleAdminDashboard}
                  className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-surface-color border border-border-color text-text-color hover:bg-purple-600 hover:text-white transition-colors duration-200"
                >
                  <Shield size={18} />
                  <span>Admin Dashboard</span>
                </button>
              )}
              
              {/* Theme Toggle Button */}
              <button
                onClick={toggleTheme}
                className="p-2 rounded-full bg-surface-color border border-border-color shadow-sm text-text-color hover:bg-primary-purple-600 hover:text-white transition-colors duration-200"
                aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              >
                {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
              </button>
              
              {/* Sign Out Button */}
              <button 
                onClick={handleLogout}
                className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-surface-color border border-border-color text-text-color hover:bg-red-500 hover:text-white transition-colors duration-200"
              >
                <LogOut size={18} />
                <span>Sign Out</span>
              </button>
            </div>
          </header>

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
                  className="flex-1 overflow-y-auto w-full max-w-2xl md:max-w-3xl lg:max-w-4xl xl:max-w-5xl 2xl:max-w-6xl mx-auto px-4"
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