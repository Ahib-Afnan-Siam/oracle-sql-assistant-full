// src/components/Login.tsx
import React, { useState } from "react";
import { Eye, EyeOff, Check, Loader2 } from "lucide-react";
import "./Login.css";

const Login = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    
    // Check for admin credentials first
    if (username === "AdminMIS" && password === "mis123") {
      setSuccess(true);
      // Store token in localStorage
      localStorage.setItem("authToken", "admin-token");
      localStorage.setItem("isAdmin", "true");
      // Redirect to admin dashboard
      setTimeout(() => {
        window.location.href = "/admin";
      }, 1000);
      return;
    }
    
    // Validate that username is a number (employee ID) for regular users
    if (!/^\d+$/.test(username)) {
      setError("Username must be a valid employee ID number");
      setLoading(false);
      return;
    }
    
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username: username,
          password: password,
        }),
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        setSuccess(true);
        // Store token in localStorage
        localStorage.setItem("authToken", data.token);
        localStorage.setItem("isAdmin", data.isAdmin ? "true" : "false");
        // Redirect to main app
        setTimeout(() => {
          window.location.href = "/app";
        }, 1000);
      } else {
        setError(data.message || "Login failed");
        // Trigger shake animation on error
        const card = document.querySelector('.login-card');
        if (card) {
          card.classList.add('shake');
          setTimeout(() => {
            card.classList.remove('shake');
          }, 500);
        }
      }
    } catch (err) {
      setError("Network error. Please try again.");
      // Trigger shake animation on error
      const card = document.querySelector('.login-card');
      if (card) {
        card.classList.add('shake');
        setTimeout(() => {
          card.classList.remove('shake');
        }, 500);
      }
      console.error("Login error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container min-h-screen flex items-center justify-center p-4">
      <div className="login-card w-full max-w-md bg-white/90 backdrop-blur-lg rounded-2xl shadow-xl p-6 sm:p-8 transition-all duration-300 hover:shadow-2xl transform transition-transform duration-700 ease-out opacity-0 translate-y-4 animate-fade-in-up">
        {/* Logo and Title */}
        <div className="text-center mb-6 sm:mb-8 animate-logo-breath">
          <div className="logo-glow"></div>
          <img 
            src="/Uttoron 1-01_v2.png" 
            alt="Uttoron" 
            className="mx-auto h-12 sm:h-16 w-auto mb-3 sm:mb-4 object-contain relative z-10"
          />
          <p className="text-gray-600 text-sm sm:text-base animate-fade-in delay-300">Ask our AI anything</p>
        </div>

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-5 sm:space-y-6">
          {error && (
            <div className="text-red-500 text-sm text-center py-2 px-4 bg-red-50 rounded-lg animate-fade-in">
              {error}
            </div>
          )}
          
          <div className="input-group animate-fade-in delay-500">
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Username (Employee ID)
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
              placeholder="Enter your employee ID (e.g., 123456)"
              required
            />
          </div>

          <div className="input-group animate-fade-in delay-700">
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 sm:px-4 sm:py-3 pr-10 sm:pr-12 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
                placeholder="••••••••"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-500 hover:text-gray-700 transition-colors duration-200"
              >
                {showPassword ? <EyeOff size={16} className="sm:w-5 sm:h-5" /> : <Eye size={16} className="sm:w-5 sm:h-5" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || success}
            className="login-button w-full bg-gradient-to-r from-primary-purple-600 to-primary-purple-700 text-white py-2.5 sm:py-3 rounded-lg font-medium hover:from-primary-purple-700 hover:to-primary-purple-800 transition-all duration-200 shadow-md hover:shadow-lg transform hover:-translate-y-0.5 disabled:opacity-100 disabled:cursor-not-allowed relative overflow-hidden text-sm sm:text-base"
          >
            <div className="button-content flex items-center justify-center">
              {success ? (
                <>
                  <Check size={16} className="mr-2 sm:w-5 sm:h-5" />
                  <span>Success</span>
                </>
              ) : loading ? (
                <>
                  <Loader2 size={16} className="mr-2 sm:w-5 sm:h-5 animate-spin" />
                  <span>Logging in...</span>
                </>
              ) : (
                "Log in"
              )}
            </div>
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;