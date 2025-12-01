import React, { useState, useEffect, useRef } from 'react';
import { Bell, Settings, Moon, Sun, User, Activity, Server, Clock, LogOut, Check, X, Plus, TrendingUp, TrendingDown, MessageSquare, Database, Zap, Users, BarChart2 } from 'react-feather';
import { useNavigate } from 'react-router-dom';
import { Tabs } from './ui';
import { Card, MetricCard, Chart, Panel, Button, Input, Grid } from './ui';
import AnalyticsDashboard from './AnalyticsDashboard';
import TokenUsageDashboard from './TokenUsageDashboard';

const AdminDashboard: React.FC = () => {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [metrics, setMetrics] = useState({
    users: { total: 0, active: 0, trend: "+0%" },
    chats: { total: 0, active: 0, completed: 0, trend: "+0%" },
    messages: { total: 0, userQueries: 0, aiResponses: 0, trend: "+0%" },
    performance: { 
      avgResponseTime: 0, 
      totalTokens: 0, 
      availableModels: 0, 
      totalQueries: 0,
      trend: "+0%" 
    },
    systemStatus: 'Operational'
  });
  const [recentActivity, setRecentActivity] = useState<any[]>([]);
  const [accessRequests, setAccessRequests] = useState<any[]>([]);
  const [authorizedUsers, setAuthorizedUsers] = useState<any[]>([]);
  const [filteredUsers, setFilteredUsers] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [usersPerPage] = useState(10);
  const [newUserId, setNewUserId] = useState('');
  const [disableUserId, setDisableUserId] = useState('');
  const [enableUserId, setEnableUserId] = useState('');
  const [grantAdminUserId, setGrantAdminUserId] = useState('');
  const [revokeAdminUserId, setRevokeAdminUserId] = useState('');
  const [loading, setLoading] = useState(false);
  const [accessRequestsMessage, setAccessRequestsMessage] = useState<{ type: string; text: string } | null>(null);
  const [directAccessMessage, setDirectAccessMessage] = useState<{ type: string; text: string } | null>(null);
  const [manageAccessMessage, setManageAccessMessage] = useState<{ type: string; text: string } | null>(null);
  const navigate = useNavigate();
  const refreshIntervalRef = useRef<number | null>(null);

  // Check if user is admin on component mount
  useEffect(() => {
    const isAdmin = localStorage.getItem("isAdmin") === "true";
    const token = localStorage.getItem("authToken");
    
    if (!isAdmin || !token) {
      // Redirect to login if not admin or no token
      navigate("/login");
      return;
    }
  }, [navigate]);

  // Toggle theme
  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    document.documentElement.classList.toggle('dark', newTheme === 'dark');
  };

  // Handle logout
  const handleLogout = async () => {
    try {
      const token = localStorage.getItem("authToken");
      if (token) {
        // Use the same pattern as other API calls with /api prefix
        await fetch("/api/admin/logout", {
          method: "POST",
          headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
          }
        });
      }
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      // Always clear local storage and redirect regardless of server response
      localStorage.removeItem("authToken");
      localStorage.removeItem("isAdmin");
      window.location.href = "/login";
    }
  };

  // Fetch dashboard overview data
  const fetchDashboardOverview = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/dashboard/overview", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log("Dashboard overview data:", data);
        
        if (data.success && data.data) {
          setMetrics({
            users: {
              total: data.data.users?.total || 0,
              active: data.data.users?.active || 0,
              trend: data.data.users?.trend || "+0%"
            },
            chats: {
              total: data.data.chats?.total || 0,
              active: data.data.chats?.active || 0,
              completed: data.data.chats?.completed || 0,
              trend: data.data.chats?.trend || "+0%"
            },
            messages: {
              total: data.data.messages?.total || 0,
              userQueries: data.data.messages?.user_queries || 0,
              aiResponses: data.data.messages?.ai_responses || 0,
              trend: data.data.messages?.trend || "+0%"
            },
            performance: {
              avgResponseTime: data.data.performance?.avg_response_time || 0,
              totalTokens: data.data.performance?.total_tokens || 0,
              availableModels: data.data.performance?.available_models || 0,
              totalQueries: data.data.performance?.total_queries || 0,
              trend: data.data.performance?.trend || "+0%"
            },
            systemStatus: data.data.system_status || 'Operational'
          });
        }
      } else {
        console.error("Failed to fetch dashboard overview. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch dashboard overview:", error);
    }
  };

  // Fetch recent activity
  const fetchRecentActivity = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/dashboard/analytics", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log("Dashboard analytics data:", data);
        
        if (data.success && data.data && data.data.recent_activity) {
          setRecentActivity(data.data.recent_activity.slice(0, 5)); // Show only top 5
        }
      } else {
        console.error("Failed to fetch recent activity. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch recent activity:", error);
    }
  };

  // Fetch access requests
  const fetchAccessRequests = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/access-requests", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log("Access requests data:", data);
        console.log("Requests array:", data.requests);
        setAccessRequests(data.requests || []);
      } else {
        console.error("Failed to fetch access requests. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch access requests:", error);
    }
  };

  // Fetch authorized users
  const fetchAuthorizedUsers = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/authorized-users", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setAuthorizedUsers(data.users || []);
        setFilteredUsers(data.users || []);
      } else {
        console.error("Failed to fetch authorized users. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch authorized users:", error);
    }
  };

  // Fetch user statistics
  const fetchUserStats = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/user-stats", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setMetrics(prevMetrics => ({
          ...prevMetrics,
          users: {
            ...prevMetrics.users,
            total: data.total_users || 0,
            active: data.active_users || 0
          }
        }));
      } else {
        console.error("Failed to fetch user statistics. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch user statistics:", error);
    }
  };

  // Fetch total chats count directly from the new endpoint
  const fetchTotalChats = async () => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/dashboard/total-chats", {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        console.log("Total chats data:", data);
        
        if (data.success && data.total_chats !== undefined) {
          setMetrics(prevMetrics => ({
            ...prevMetrics,
            chats: {
              ...prevMetrics.chats,
              total: data.total_chats
            }
          }));
        }
      } else {
        console.error("Failed to fetch total chats. Status:", response.status);
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Failed to fetch total chats:", error);
    }
  };

  // Set up auto-refresh for dashboard data
  useEffect(() => {
    // Fetch data immediately on mount
    fetchDashboardOverview();
    fetchRecentActivity();
    fetchTotalChats(); // Fetch total chats using the new endpoint
    
    // Set up 30-second interval for auto-refresh
    const interval = window.setInterval(() => {
      fetchDashboardOverview();
      fetchRecentActivity();
      fetchTotalChats(); // Refresh total chats using the new endpoint
    }, 30000); // 30 seconds
    
    refreshIntervalRef.current = interval;

    // Clean up interval on unmount
    return () => {
      if (refreshIntervalRef.current) {
        window.clearInterval(refreshIntervalRef.current);
      }
    };
  }, []);

  // Filter users based on search term
  useEffect(() => {
    if (!searchTerm) {
      setFilteredUsers(authorizedUsers);
      setCurrentPage(1);
      return;
    }
    
    const filtered = authorizedUsers.filter(user => 
      user.USER_ID.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.FULL_NAME.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (user.DEPARTMENT && user.DEPARTMENT.toLowerCase().includes(searchTerm.toLowerCase()))
    );
    
    setFilteredUsers(filtered);
    setCurrentPage(1);
  }, [searchTerm, authorizedUsers]);

  // Render chart when component mounts
  useEffect(() => {
    const renderChart = () => {
      const canvas = document.getElementById('user-activity-chart') as HTMLCanvasElement;
      if (!canvas) return;
      
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      
      // Clear previous chart
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      // Chart dimensions
      const width = canvas.width;
      const height = canvas.height;
      const padding = 40;
      
      // Data points
      const data = [12, 19, 3, 5, 2, 3];
      const labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
      
      // Find max value for scaling
      const maxVal = Math.max(...data);
      
      // Draw grid lines
      ctx.strokeStyle = '#e5e7eb';
      ctx.lineWidth = 1;
      
      // Horizontal grid lines
      for (let i = 0; i <= 5; i++) {
        const y = padding + (height - 2 * padding) * (1 - i / 5);
        ctx.beginPath();
        ctx.moveTo(padding, y);
        ctx.lineTo(width - padding, y);
        ctx.stroke();
        
        // Draw Y-axis labels
        ctx.fillStyle = '#6b7280';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(Math.round(maxVal * i / 5).toString(), padding - 10, y + 4);
      }
      
      // Vertical grid lines and labels
      const step = (width - 2 * padding) / (labels.length - 1);
      for (let i = 0; i < labels.length; i++) {
        const x = padding + i * step;
        
        // Draw vertical grid line
        ctx.beginPath();
        ctx.moveTo(x, padding);
        ctx.lineTo(x, height - padding);
        ctx.stroke();
        
        // Draw X-axis labels
        ctx.fillStyle = '#6b7280';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(labels[i], x, height - padding + 20);
      }
      
      // Draw line chart
      ctx.beginPath();
      ctx.strokeStyle = '#7c3aed';
      ctx.lineWidth = 2;
      
      const pointRadius = 4;
      
      for (let i = 0; i < data.length; i++) {
        const x = padding + (width - 2 * padding) * (i / (data.length - 1));
        const y = padding + (height - 2 * padding) * (1 - data[i] / maxVal);
        
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        
        // Draw data points
        ctx.fillStyle = '#7c3aed';
        ctx.beginPath();
        ctx.arc(x, y, pointRadius, 0, Math.PI * 2);
        ctx.fill();
      }
      
      ctx.stroke();
      
      // Draw title
      ctx.fillStyle = '#1f2937';
      ctx.font = '16px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Active Users', width / 2, 20);
    };
    
    // Render chart after a short delay to ensure DOM is ready
    const timeoutId = setTimeout(renderChart, 100);
    
    // Re-render on window resize
    const handleResize = () => {
      clearTimeout(timeoutId);
      setTimeout(renderChart, 100);
    };
    
    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      clearTimeout(timeoutId);
    };
  }, []);

  // Handle approve request
  const handleApproveRequest = async (requestId: number) => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch(`/api/admin/approve-request/${requestId}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        }
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setAccessRequestsMessage({ type: "success", text: "User access request approved successfully" });
        fetchAccessRequests(); // Refresh the list
        fetchUserStats(); // Refresh user statistics
      } else {
        setAccessRequestsMessage({ type: "error", text: data.message || "Failed to approve access request" });
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Error approving request:", error);
      setAccessRequestsMessage({ type: "error", text: "Error approving access request" });
    }
  };

  // Handle deny request
  const handleDenyRequest = async (requestId: number) => {
    try {
      const token = localStorage.getItem("authToken");
      const response = await fetch(`/api/admin/deny-request/${requestId}`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        }
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setAccessRequestsMessage({ type: "success", text: "User access request denied successfully" });
        fetchAccessRequests(); // Refresh the list
        fetchUserStats(); // Refresh user statistics
      } else {
        setAccessRequestsMessage({ type: "error", text: data.message || "Failed to deny access request" });
        // If we get a 403, redirect to login
        if (response.status === 403) {
          localStorage.removeItem("authToken");
          localStorage.removeItem("isAdmin");
          window.location.href = "/login";
        }
      }
    } catch (error) {
      console.error("Error denying request:", error);
      setAccessRequestsMessage({ type: "error", text: "Error denying access request" });
    }
  };

  // Handle add user directly
  const handleAddUser = async () => {
    if (!newUserId) {
      setDirectAccessMessage({ type: "error", text: "Please enter a User ID" });
      return;
    }

    try {
      setLoading(true);
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/add-user", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ user_id: newUserId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setDirectAccessMessage({ type: "success", text: "User added successfully" });
        setNewUserId('');
        // Refresh the authorized users list
        fetchAuthorizedUsers();
        fetchUserStats(); // Refresh user statistics
      } else {
        setDirectAccessMessage({ type: "error", text: data.message || "Failed to add user" });
      }
    } catch (error) {
      console.error("Error adding user:", error);
      setDirectAccessMessage({ type: "error", text: "Error adding user" });
    } finally {
      setLoading(false);
    }
  };

  // Handle disable user access
  const handleDisableUser = async () => {
    if (!disableUserId) {
      setManageAccessMessage({ type: "error", text: "Please enter a User ID to disable" });
      return;
    }

    try {
      setLoading(true);
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/disable-user", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ user_id: disableUserId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setManageAccessMessage({ type: "success", text: data.message });
        setDisableUserId('');
        // Refresh the authorized users list
        fetchAuthorizedUsers();
        fetchUserStats(); // Refresh user statistics
      } else {
        setManageAccessMessage({ type: "error", text: data.message || "Failed to disable user access" });
      }
    } catch (error) {
      console.error("Error disabling user:", error);
      setManageAccessMessage({ type: "error", text: "Error disabling user access" });
    } finally {
      setLoading(false);
    }
  };

  // Handle enable user access
  const handleEnableUser = async () => {
    if (!enableUserId) {
      setManageAccessMessage({ type: "error", text: "Please enter a User ID to enable" });
      return;
    }

    try {
      setLoading(true);
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/enable-user", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ user_id: enableUserId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setManageAccessMessage({ type: "success", text: data.message });
        setEnableUserId('');
        // Refresh the authorized users list
        fetchAuthorizedUsers();
        fetchUserStats(); // Refresh user statistics
      } else {
        setManageAccessMessage({ type: "error", text: data.message || "Failed to enable user access" });
      }
    } catch (error) {
      console.error("Error enabling user:", error);
      setManageAccessMessage({ type: "error", text: "Error enabling user access" });
    } finally {
      setLoading(false);
    }
  };

  // Handle grant admin access
  const handleGrantAdminAccess = async () => {
    if (!grantAdminUserId) {
      setManageAccessMessage({ type: "error", text: "Please enter a User ID to grant admin access" });
      return;
    }

    try {
      setLoading(true);
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/grant-admin-access", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ user_id: grantAdminUserId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setManageAccessMessage({ type: "success", text: data.message });
        setGrantAdminUserId('');
        // Refresh the authorized users list
        fetchAuthorizedUsers();
        fetchUserStats(); // Refresh user statistics
      } else {
        setManageAccessMessage({ type: "error", text: data.message || "Failed to grant admin access" });
      }
    } catch (error) {
      console.error("Error granting admin access:", error);
      setManageAccessMessage({ type: "error", text: "Error granting admin access" });
    } finally {
      setLoading(false);
    }
  };

  // Handle revoke admin access
  const handleRevokeAdminAccess = async () => {
    if (!revokeAdminUserId) {
      setManageAccessMessage({ type: "error", text: "Please enter a User ID to revoke admin access" });
      return;
    }

    try {
      setLoading(true);
      const token = localStorage.getItem("authToken");
      const response = await fetch("/api/admin/revoke-admin-access", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ user_id: revokeAdminUserId })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setManageAccessMessage({ type: "success", text: data.message });
        setRevokeAdminUserId('');
        // Refresh the authorized users list
        fetchAuthorizedUsers();
        fetchUserStats(); // Refresh user statistics
      } else {
        setManageAccessMessage({ type: "error", text: data.message || "Failed to revoke admin access" });
      }
    } catch (error) {
      console.error("Error revoking admin access:", error);
      setManageAccessMessage({ type: "error", text: "Error revoking admin access" });
    } finally {
      setLoading(false);
    }
  };

  // Fetch access requests on component mount
  useEffect(() => {
    const isAdmin = localStorage.getItem("isAdmin") === "true";
    const token = localStorage.getItem("authToken");
    
    if (isAdmin && token) {
      fetchAccessRequests();
      fetchAuthorizedUsers();
      fetchUserStats(); // Fetch user statistics on component mount
    }
  }, []);

  return (
    <div className="min-h-screen bg-background-color text-text-color">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-4">
            <div className="flex items-center">
              <div className="flex items-center">
                <img 
                  src="/Uttoron 1-01_v2.png" 
                  alt="Uttoron Logo" 
                  className="h-10 w-auto"
                />
              </div>
              <h1 className="ml-6 text-2xl font-bold text-gray-800 dark:text-white">Admin Dashboard</h1>
            </div>
            <div className="flex items-center space-x-4">
              <button className="p-2 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-purple-100 dark:hover:bg-purple-900 transition-colors">
                <Bell size={20} />
              </button>
              <button className="p-2 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-purple-100 dark:hover:bg-purple-900 transition-colors">
                <Settings size={20} />
              </button>
              <button 
                onClick={toggleTheme}
                className="p-2 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-purple-100 dark:hover:bg-purple-900 transition-colors"
              >
                {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
              </button>
              <button 
                onClick={() => navigate("/app")}
                className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-surface-color border border-border-color text-text-color hover:bg-purple-600 hover:text-white transition-colors duration-200"
              >
                <MessageSquare size={18} />
                <span>Back To Chat</span>
              </button>
              <button 
                onClick={handleLogout}
                className="flex items-center space-x-1 px-3 py-2 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors"
              >
                <LogOut size={18} />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs 
          tabs={[
            {
              id: 'dashboard',
              label: 'Dashboard',
              content: (
                <div className="space-y-6">
                  {/* Metrics Cards */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-6">
                    <MetricCard 
                      title="Total Users" 
                      value={metrics.users.total} 
                      icon={<Users className="h-6 w-6 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.users.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="Active Users" 
                      value={metrics.users.active} 
                      icon={<Activity className="h-6 w-6 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.users.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="Total Chats" 
                      value={metrics.chats.total} 
                      icon={<MessageSquare className="h-6 w-6 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.chats.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="Avg Response Time" 
                      value={`${metrics.performance.avgResponseTime}ms`} 
                      icon={<Zap className="h-6 w-6 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.performance.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="System Status" 
                      value={metrics.systemStatus} 
                      icon={<Server className="h-6 w-6 text-green-600 dark:text-green-400" />}
                      className="h-full"
                    />
                  </div>

                  {/* Charts and Activity */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
                      <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">User Activity</h3>
                        <Button variant="secondary" size="sm">View Details</Button>
                      </div>
                      <div className="h-80 flex items-center justify-center">
                        <canvas id="user-activity-chart" className="w-full h-full"></canvas>
                      </div>
                    </div>

                    <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
                      <div className="flex justify-between items-center mb-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Activity</h3>
                        <Button variant="secondary" size="sm">View All</Button>
                      </div>
                      <div className="space-y-4">
                        {recentActivity.length > 0 ? (
                          recentActivity.map((activity, index) => (
                            <div key={index} className="flex items-start">
                              <div className="flex-shrink-0 mt-1">
                                <div className="w-3 h-3 rounded-full bg-purple-500"></div>
                              </div>
                              <div className="ml-3">
                                <p className="text-sm font-medium text-gray-900 dark:text-white">
                                  {activity.data?.action || activity.action || 'System event'}
                                </p>
                                <p className="text-xs text-gray-500 dark:text-gray-400">
                                  {activity.timestamp ? new Date(activity.timestamp).toLocaleString() : 'Just now'}
                                </p>
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                            <p>No recent activity</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Additional Metrics */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    <MetricCard 
                      title="Total Messages" 
                      value={metrics.messages.total} 
                      icon={<MessageSquare className="h-5 w-5 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.messages.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="User Queries" 
                      value={metrics.messages.userQueries} 
                      icon={<User className="h-5 w-5 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.messages.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="AI Responses" 
                      value={metrics.messages.aiResponses} 
                      icon={<Server className="h-5 w-5 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.messages.trend}
                      className="h-full"
                    />
                    <MetricCard 
                      title="Total Tokens" 
                      value={metrics.performance.totalTokens.toLocaleString()} 
                      icon={<Database className="h-5 w-5 text-purple-600 dark:text-purple-400" />}
                      trend={metrics.performance.trend}
                      className="h-full"
                    />
                  </div>
                </div>
              )
            },
            {
              id: 'user-management',
              label: 'User Management',
              content: (
                <div className="space-y-4">
                  {/* User Access Control Section */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="flex flex-col">
                      {/* Direct User Access */}
                      <Panel title="Direct User Access" className="flex flex-col flex-1 h-full">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                          Manually add a user to the access list by entering their HRIS User ID
                        </p>
                        
                        {directAccessMessage && directAccessMessage.type === "success" && (
                          <div className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded">
                            {directAccessMessage.text}
                          </div>
                        )}
                        
                        {directAccessMessage && directAccessMessage.type === "error" && (
                          <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded">
                            {directAccessMessage.text}
                          </div>
                        )}
                        
                        <div className="flex space-x-2 flex-1 items-end">
                          <Input
                            type="text"
                            value={newUserId}
                            onChange={(e) => setNewUserId(e.target.value)}
                            placeholder="Enter HRIS User ID"
                            disabled={loading}
                            fullWidth
                          />
                          <Button
                            onClick={handleAddUser}
                            disabled={loading}
                            loading={loading}
                          >
                            <Plus size={16} className="mr-1" />
                            Add User
                          </Button>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                          This will grant immediate access to the user without requiring approval
                        </p>
                      </Panel>
                    </div>

                    <div className="flex flex-col">
                      {/* Manage User Access */}
                      <Panel title="Manage User Access" className="flex flex-col flex-1 h-full">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                          Temporarily or permanently turn off chatbot access for a user.
                        </p>
                        
                        {manageAccessMessage && manageAccessMessage.type === "success" && (
                          <div className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded">
                            {manageAccessMessage.text}
                          </div>
                        )}
                        
                        {manageAccessMessage && manageAccessMessage.type === "error" && (
                          <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded">
                            {manageAccessMessage.text}
                          </div>
                        )}
                        
                        <div className="space-y-4 flex-1 flex flex-col justify-between">
                          {/* Disable User Access */}
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Disable User Access
                            </label>
                            <div className="flex space-x-2">
                              <Input
                                type="text"
                                value={disableUserId}
                                onChange={(e) => setDisableUserId(e.target.value)}
                                placeholder="Enter HRIS User ID"
                                disabled={loading}
                                fullWidth
                              />
                              <Button
                                variant="danger"
                                onClick={handleDisableUser}
                                disabled={loading}
                                loading={loading}
                              >
                                <span className="mr-1">🔴</span>
                                Disable Access
                              </Button>
                            </div>
                          </div>
                          
                          {/* Enable User Access */}
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Enable User Access
                            </label>
                            <div className="flex space-x-2">
                              <Input
                                type="text"
                                value={enableUserId}
                                onChange={(e) => setEnableUserId(e.target.value)}
                                placeholder="Enter HRIS User ID"
                                disabled={loading}
                                fullWidth
                              />
                              <Button
                                variant="success"
                                onClick={handleEnableUser}
                                disabled={loading}
                                loading={loading}
                              >
                                <span className="mr-1">🟢</span>
                                Enable Access
                              </Button>
                            </div>
                          </div>
                        </div>
                      </Panel>
                    </div>
                    
                    <div className="flex flex-col">
                      {/* Manage Admin Access */}
                      <Panel title="Manage Admin Access" className="flex flex-col flex-1 h-full">
                        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                          Grant or revoke admin privileges for a user.
                        </p>
                        
                        {manageAccessMessage && manageAccessMessage.type === "success" && (
                          <div className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded">
                            {manageAccessMessage.text}
                          </div>
                        )}
                        
                        {manageAccessMessage && manageAccessMessage.type === "error" && (
                          <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded">
                            {manageAccessMessage.text}
                          </div>
                        )}
                        
                        <div className="space-y-4 flex-1 flex flex-col justify-between">
                          {/* Grant Admin Access */}
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Grant Admin Access
                            </label>
                            <div className="flex space-x-2">
                              <Input
                                type="text"
                                value={grantAdminUserId}
                                onChange={(e) => setGrantAdminUserId(e.target.value)}
                                placeholder="Enter HRIS User ID"
                                disabled={loading}
                                fullWidth
                              />
                              <Button
                                variant="success"
                                onClick={handleGrantAdminAccess}
                                disabled={loading}
                                loading={loading}
                              >
                                <span className="mr-1">👑</span>
                                Grant Admin
                              </Button>
                            </div>
                          </div>
                          
                          {/* Revoke Admin Access */}
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Revoke Admin Access
                            </label>
                            <div className="flex space-x-2">
                              <Input
                                type="text"
                                value={revokeAdminUserId}
                                onChange={(e) => setRevokeAdminUserId(e.target.value)}
                                placeholder="Enter HRIS User ID"
                                disabled={loading}
                                fullWidth
                              />
                              <Button
                                variant="danger"
                                onClick={handleRevokeAdminAccess}
                                disabled={loading}
                                loading={loading}
                              >
                                <span className="mr-1">👤</span>
                                Revoke Admin
                              </Button>
                            </div>
                          </div>
                        </div>
                      </Panel>
                    </div>
                  </div>
                  
                  {/* Pending User Access Requests - Second Row */}
                  <div className="grid grid-cols-1 gap-4">
                    <div className="flex flex-col">
                      {/* Pending User Access Requests */}
                      <Panel 
                        title="Pending User Access Requests" 
                        headerActions={
                          <Button 
                            variant="secondary" 
                            size="sm" 
                            onClick={fetchAccessRequests}
                          >
                            Refresh
                          </Button>
                        }
                        className="flex flex-col flex-1 h-full"
                      >
                        {accessRequestsMessage && accessRequestsMessage.type === "success" && (
                          <div className="mb-4 p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded">
                            {accessRequestsMessage.text}
                          </div>
                        )}
                        
                        {accessRequestsMessage && accessRequestsMessage.type === "error" && (
                          <div className="mb-4 p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded">
                            {accessRequestsMessage.text}
                          </div>
                        )}
                        
                        {accessRequests.length === 0 ? (
                          <div className="text-center py-8 text-gray-500 dark:text-gray-400 flex-1 flex items-center justify-center">
                            <p>No pending access requests</p>
                          </div>
                        ) : (
                          <div className="overflow-x-auto flex-1">
                            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                              <thead className="bg-gray-50 dark:bg-gray-700">
                                <tr>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">User ID</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Name</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Email</th>
                                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Actions</th>
                                </tr>
                              </thead>
                              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                {accessRequests.map((request) => {
                                  console.log("Rendering request:", request);
                                  return (
                                    <tr key={request.ID}>
                                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{request.USER_ID}</td>
                                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{request.FULL_NAME}</td>
                                      <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{request.EMAIL}</td>
                                      <td className="px-4 py-3 text-sm">
                                        <div className="flex space-x-2">
                                          <Button 
                                            variant="success" 
                                            size="sm" 
                                            onClick={() => handleApproveRequest(request.ID)}
                                            title="Approve"
                                          >
                                            <Check size={16} />
                                          </Button>
                                          <Button 
                                            variant="danger" 
                                            size="sm" 
                                            onClick={() => handleDenyRequest(request.ID)}
                                            title="Deny"
                                          >
                                            <X size={16} />
                                          </Button>
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </Panel>
                    </div>
                  </div>
                </div>
              )
            },
            {
              id: 'user-list',
              label: 'Accessed Users',
              content: (
                <Panel 
                  title="Accessed User List" 
                  headerActions={
                    <div className="flex space-x-2">
                      <Input
                        type="text"
                        placeholder="Search by User ID, Name, or Department"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-64"
                      />
                      <Button 
                        variant="secondary" 
                        onClick={fetchAuthorizedUsers}
                      >
                        Refresh
                      </Button>
                    </div>
                  }
                >
                  {filteredUsers.length === 0 ? (
                    <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                      <p>No authorized users found</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                          <thead className="bg-gray-50 dark:bg-gray-700">
                            <tr>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">User ID</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Full Name</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Email</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Designation</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Department</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Role</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Date Added</th>
                            </tr>
                          </thead>
                          <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                            {filteredUsers.slice(
                              (currentPage - 1) * usersPerPage,
                              currentPage * usersPerPage
                            ).map((user) => (
                              <tr key={user.ID}>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{user.USER_ID}</td>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{user.FULL_NAME}</td>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{user.EMAIL}</td>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{user.DESIGNATION || '-'}</td>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">{user.DEPARTMENT || '-'}</td>
                                <td className="px-4 py-3 text-sm">
                                  {user.is_admin ? (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                                      👑 Admin
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                      👤 User
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-sm">
                                  {user.STATUS === 'Y' ? (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                      🟢 Active
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                                      🔴 Disabled
                                    </span>
                                  )}
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-900 dark:text-gray-900">
                                  {user.CREATED_AT ? new Date(user.CREATED_AT).toLocaleDateString() : '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      
                      {/* Pagination */}
                      {filteredUsers.length > usersPerPage && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          <div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Showing {Math.min((currentPage - 1) * usersPerPage + 1, filteredUsers.length)} to {Math.min(currentPage * usersPerPage, filteredUsers.length)} of {filteredUsers.length} entries
                            </div>
                          </div>
                          <div>
                            <div className="flex justify-end space-x-1">
                              <Button
                                onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                                disabled={currentPage === 1}
                                variant="secondary"
                              >
                                Previous
                              </Button>
                              <Button
                                onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(filteredUsers.length / usersPerPage)))}
                                disabled={currentPage === Math.ceil(filteredUsers.length / usersPerPage)}
                                variant="secondary"
                              >
                                Next
                              </Button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Panel>
              )
            },
          {
            id: 'analytics',
            label: 'Analytics & Insights',
            content: (
              <AnalyticsDashboard />
            )
          },
          {
            id: 'token-usage',
            label: 'Token Usage',
            content: (
              <TokenUsageDashboard />
            )
          }
        ]}
        defaultTab="dashboard"
      />
    </main>
  </div>
);
};

export default AdminDashboard;