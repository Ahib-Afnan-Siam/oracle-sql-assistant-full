import React, { useState, useEffect } from 'react';
import { Bell, Settings, Moon, Sun, User, Activity, Server, Clock, LogOut, Check, X, Plus, TrendingUp } from 'react-feather';
import { useNavigate } from 'react-router-dom';

const AdminDashboard: React.FC = () => {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [metrics, setMetrics] = useState({
    users: 124,
    chats: 864,
    activeUsers: 42,
    serverStatus: 'Operational'
  });
  const [recentActivity, setRecentActivity] = useState([
    { date: '10/11', time: '10:30 AM', action: 'User JohnDoe registered' },
    { date: '10/11', time: '09:45 AM', action: 'System maintenance completed' },
    { date: '09/11', time: '04:20 PM', action: 'New chat session started' },
    { date: '09/11', time: '02:15 PM', action: 'Database backup completed' },
    { date: '08/11', time: '11:30 AM', action: 'User JaneSmith approved' }
  ]);
  const [accessRequests, setAccessRequests] = useState<any[]>([]);
  const [authorizedUsers, setAuthorizedUsers] = useState<any[]>([]);
  const [filteredUsers, setFilteredUsers] = useState<any[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [usersPerPage] = useState(10);
  const [newUserId, setNewUserId] = useState('');
  const [disableUserId, setDisableUserId] = useState('');
  const [enableUserId, setEnableUserId] = useState('');
  const [loading, setLoading] = useState(false);
  const [accessRequestsMessage, setAccessRequestsMessage] = useState<{ type: string; text: string } | null>(null);
  const [directAccessMessage, setDirectAccessMessage] = useState<{ type: string; text: string } | null>(null);
  const [manageAccessMessage, setManageAccessMessage] = useState<{ type: string; text: string } | null>(null);
  const navigate = useNavigate();

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
          users: data.total_users || 0,
          activeUsers: data.active_users || 0
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
                <div className="bg-purple-600 rounded-full p-2">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <span className="ml-2 text-xl font-bold text-purple-600 dark:text-purple-400">Uttoron</span>
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
        {/* Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <User className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Users</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics.users}</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Chats</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics.chats}</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <Activity className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Users</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics.activeUsers}</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-green-100 dark:bg-green-900">
                <Server className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Server Status</p>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">{metrics.serverStatus}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Charts and Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* User Activity Chart */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">User Activity</h2>
            <div className="h-64 flex items-center justify-center">
              <div className="text-center">
                <Activity className="h-12 w-12 text-purple-500 mx-auto mb-2" />
                <p className="text-gray-500 dark:text-gray-400">User activity chart visualization</p>
                <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">Line chart showing engagement over time</p>
              </div>
            </div>
          </div>

          {/* System Logs */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">System Logs</h2>
              <button className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors">
                Settings
              </button>
            </div>
            <div className="space-y-4">
              {recentActivity.map((activity, index) => (
                <div key={index} className="flex items-center justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
                  <div className="flex items-center">
                    <div className="flex-shrink-0 w-10 h-10 rounded-md border border-purple-200 dark:border-purple-800 flex items-center justify-center">
                      <span className="text-xs font-medium text-purple-600 dark:text-purple-400">{activity.date}</span>
                    </div>
                    <div className="ml-4">
                      <p className="text-sm font-medium text-gray-900 dark:text-white">{activity.action}</p>
                    </div>
                  </div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">{activity.time}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* User Access Control Section */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
          {/* Pending User Access Requests */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Pending User Access Requests</h2>
              <button 
                onClick={fetchAccessRequests}
                className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                Refresh
              </button>
            </div>
            
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
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <p>No pending access requests</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
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
                              <button
                                onClick={() => handleApproveRequest(request.ID)}
                                className="p-1 text-green-600 hover:text-green-800 dark:hover:text-green-400"
                                title="Approve"
                              >
                                <Check size={16} />
                              </button>
                              <button
                                onClick={() => handleDenyRequest(request.ID)}
                                className="p-1 text-red-600 hover:text-red-800 dark:hover:text-red-400"
                                title="Deny"
                              >
                                <X size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Direct User Access */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Direct User Access</h2>
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
            
            <div className="flex space-x-2">
              <input
                type="text"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                placeholder="Enter HRIS User ID"
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                disabled={loading}
              />
              <button
                onClick={handleAddUser}
                disabled={loading}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Adding...
                  </>
                ) : (
                  <>
                    <Plus size={16} className="mr-1" />
                    Add User
                  </>
                )}
              </button>
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
              This will grant immediate access to the user without requiring approval
            </p>
          </div>

          {/* Manage User Access */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Manage User Access</h2>
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
            
            <div className="space-y-4">
              {/* Disable User Access */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Disable User Access
                </label>
                <div className="flex space-x-2">
                  <input
                    type="text"
                    value={disableUserId}
                    onChange={(e) => setDisableUserId(e.target.value)}
                    placeholder="Enter HRIS User ID"
                    className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    disabled={loading}
                  />
                  <button
                    onClick={handleDisableUser}
                    disabled={loading}
                    className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center"
                  >
                    {loading ? (
                      <>
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Disabling...
                      </>
                    ) : (
                      <>
                        <span className="mr-1">🔴</span>
                        Disable Access
                      </>
                    )}
                  </button>
                </div>
              </div>
              
              {/* Enable User Access */}
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Enable User Access
                </label>
                <div className="flex space-x-2">
                  <input
                    type="text"
                    value={enableUserId}
                    onChange={(e) => setEnableUserId(e.target.value)}
                    placeholder="Enter HRIS User ID"
                    className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    disabled={loading}
                  />
                  <button
                    onClick={handleEnableUser}
                    disabled={loading}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 flex items-center"
                  >
                    {loading ? (
                      <>
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Enabling...
                      </>
                    ) : (
                      <>
                        <span className="mr-1">🟢</span>
                        Enable Access
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Additional Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <User className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Users</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics.users}</p>
                <p className="text-sm text-green-500 flex items-center mt-1">
                  <TrendingUp size={16} className="mr-1" />
                  <span>+5%</span>
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Chats</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{metrics.chats}</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <Clock className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Response Time</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">120ms</p>
              </div>
            </div>
          </div>
        </div>

        {/* System Status */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System Status</h2>
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-purple-600 dark:text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c-.94 1.543.826 3.31 2.37 2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <div className="ml-4">
                <p className="text-lg font-medium text-gray-900 dark:text-white">Operational</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">System is functioning normally</p>
              </div>
            </div>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Response Time</h2>
            <div className="flex items-center">
              <div className="p-3 rounded-full bg-purple-100 dark:bg-purple-900">
                <Clock className="h-6 w-6 text-purple-600 dark:text-purple-400" />
              </div>
              <div className="ml-4">
                <p className="text-2xl font-bold text-gray-900 dark:text-white">120ms</p>
                <p className="text-sm text-gray-500 dark:text-gray-400">Average response time</p>
              </div>
            </div>
          </div>
        </div>

        {/* Accessed User List */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 border border-gray-200 dark:border-gray-700 mt-8">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Accessed User List</h2>
            <div className="flex space-x-2">
              <input
                type="text"
                placeholder="Search by User ID, Name, or Department"
                className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <button 
                onClick={fetchAuthorizedUsers}
                className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                Refresh
              </button>
            </div>
          </div>
          
          {filteredUsers.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <p>No authorized users found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">User ID</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Full Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Email</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Designation</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Department</th>
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
              
              {/* Pagination */}
              {filteredUsers.length > usersPerPage && (
                <div className="flex justify-between items-center mt-4">
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Showing {Math.min((currentPage - 1) * usersPerPage + 1, filteredUsers.length)} to {Math.min(currentPage * usersPerPage, filteredUsers.length)} of {filteredUsers.length} entries
                  </div>
                  <div className="flex space-x-1">
                    <button
                      onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                      disabled={currentPage === 1}
                      className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setCurrentPage(prev => Math.min(prev + 1, Math.ceil(filteredUsers.length / usersPerPage)))}
                      disabled={currentPage === Math.ceil(filteredUsers.length / usersPerPage)}
                      className="px-3 py-1 text-sm bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default AdminDashboard;