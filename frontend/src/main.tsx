// src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import "./theme.css";
import "@fontsource/inter";

import { ChatProvider } from "./components/ChatContext"; // ✅ make sure this exists
import { ThemeProvider } from "./components/ThemeContext";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <ChatProvider>
        <App />
      </ChatProvider>
    </ThemeProvider>
  </StrictMode>
);