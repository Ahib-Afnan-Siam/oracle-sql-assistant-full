// src/components/Register.tsx
import React, { useState } from "react";
import { Eye, EyeOff, Check, Loader2 } from "lucide-react";
import "./Login.css";

const Register = () => {
  const [userId, setUserId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [designation, setDesignation] = useState("");
  const [department, setDepartment] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [emailError, setEmailError] = useState("");

  const validateEmail = (email: string) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setEmail(value);
    
    if (value && !validateEmail(value)) {
      setEmailError("Please enter a valid email address");
    } else {
      setEmailError("");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    
    // Validate email
    if (!validateEmail(email)) {
      setError("Please enter a valid email address");
      setLoading(false);
      return;
    }
    
    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          user_id: userId,
          full_name: name,  // Changed from 'name' to 'full_name' to match backend expectations
          email: email,
          designation: designation,
          department: department,
        }),
      });
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        setSuccess(true);
        // Show a more informative success message
        setError("Registration request submitted successfully. Waiting for admin approval.");
        // Redirect to login page after successful registration
        setTimeout(() => {
          window.location.href = "/login";
        }, 3000);
      } else {
        setError(data.message || "Registration failed");
        // Trigger shake animation on error
        const card = document.querySelector('.register-card');
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
      const card = document.querySelector('.register-card');
      if (card) {
        card.classList.add('shake');
        setTimeout(() => {
          card.classList.remove('shake');
        }, 500);
      }
      console.error("Registration error:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container min-h-screen flex items-center justify-center p-4">
      <div className="register-card w-full max-w-md bg-white/90 backdrop-blur-lg rounded-2xl shadow-xl p-6 sm:p-8 transition-all duration-300 hover:shadow-2xl transform transition-transform duration-700 ease-out opacity-0 translate-y-4 animate-fade-in-up">
        {/* Logo and Title */}
        <div className="text-center mb-6 sm:mb-8 animate-logo-breath">
          <div className="logo-glow"></div>
          <img 
            src="/Uttoron 1-01_v2.png" 
            alt="Uttoron" 
            className="mx-auto h-12 sm:h-16 w-auto mb-3 sm:mb-4 object-contain relative z-10"
          />
          <p className="text-gray-600 text-sm sm:text-base animate-fade-in delay-300">Register New User</p>
        </div>

        {/* Registration Form */}
        <form onSubmit={handleSubmit} className="space-y-5 sm:space-y-6">
          {error && !success && (
            <div className="text-red-500 text-sm text-center py-2 px-4 bg-red-50 rounded-lg animate-fade-in">
              {error}
            </div>
          )}
          
          {success && (
            <div className="text-green-700 text-sm text-center py-2 px-4 bg-green-50 rounded-lg animate-fade-in">
              Registration request submitted successfully. Waiting for admin approval.
            </div>
          )}
          
          <div className="input-group animate-fade-in delay-500">
            <label htmlFor="userId" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Employee ID
            </label>
            <input
              id="userId"
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              className="w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
              placeholder="Enter unique employee ID"
              required
            />
          </div>
          
          <div className="input-group animate-fade-in delay-500">
            <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Full Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
              placeholder="Enter your full name"
              required
            />
          </div>
          
          <div className="input-group animate-fade-in delay-700">
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Official Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={handleEmailChange}
              className={`w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border transition-all duration-200 bg-white/80 input-field text-sm sm:text-base ${
                emailError ? "border-red-300 focus:ring-2 focus:ring-red-500 focus:border-red-500" : "border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500"
              }`}
              placeholder="Enter your official email address"
              required
            />
            {emailError && (
              <p className="mt-1 text-sm text-red-600">{emailError}</p>
            )}
          </div>
          
          <div className="input-group animate-fade-in delay-700">
            <label htmlFor="designation" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Designation (Optional)
            </label>
            <input
              id="designation"
              type="text"
              value={designation}
              onChange={(e) => setDesignation(e.target.value)}
              className="w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
              placeholder="Enter your designation (e.g., Sub Asst. Manager)"
            />
          </div>
          
          <div className="input-group animate-fade-in delay-700">
            <label htmlFor="department" className="block text-sm font-medium text-gray-700 mb-2 transition-all duration-300">
              Department (Optional)
            </label>
            <input
              id="department"
              type="text"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="w-full px-3 py-2 sm:px-4 sm:py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-primary-purple-500 focus:border-primary-purple-500 transition-all duration-200 bg-white/80 input-field text-sm sm:text-base"
              placeholder="Enter your department"
            />
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
                  <span>Registering...</span>
                </>
              ) : (
                "Register"
              )}
            </div>
          </button>
          
          <p className="text-center text-xs text-gray-500 mt-4">
            Only authorized personnel can create new users.
          </p>
        </form>
      </div>
    </div>
  );
};

export default Register;