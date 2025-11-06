// src/components/AdminProtectedRoute.tsx
import React from "react";
import { Navigate } from "react-router-dom";

interface AdminProtectedRouteProps {
  children: React.ReactNode;
}

const AdminProtectedRoute: React.FC<AdminProtectedRouteProps> = ({ children }) => {
  const token = localStorage.getItem("authToken");
  const isAdmin = localStorage.getItem("isAdmin") === "true";
  
  if (!token || !isAdmin) {
    // User is not authenticated as admin, redirect to login
    return <Navigate to="/login" replace />;
  }
  
  // User is authenticated as admin, render the protected content
  return <>{children}</>;
};

export default AdminProtectedRoute;